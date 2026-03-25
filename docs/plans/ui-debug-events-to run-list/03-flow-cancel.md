# Flow 3: User Cancels a Running Job

## Summary

User clicks Cancel on a running eval → frontend calls `POST /api/jobs/{id}/cancel` → backend sets `job.status = "cancelled"` and attempts `UPDATE eval_runs SET status='cancelled' WHERE job_id=... AND status='running'` in the same transaction → frontend optimistically updates local state to "cancelled" → polling loop detects terminal job, re-fetches eval_run → if eval_run was properly updated, page shows "Cancelled"; if orphaned (still "running"), page reverts to stuck "Running" state.

Meanwhile, the worker's cooperative cancellation (`is_job_cancelled()` check at each iteration) detects the cancel and raises `JobCancelledError`, whose handler also sets the eval_run to "cancelled". This is a second, delayed update that works as a safety net — but only if the worker is still alive and actively processing.

**Critical finding**: There are TWO independent mechanisms that set the eval_run to "cancelled", and BOTH can fail, leaving the eval_run orphaned in "running" forever.

---

## Step-by-Step Trace

### Phase A: Frontend — User Clicks Cancel

#### From RunDetail page (`RunDetail.tsx`, line 246-260)

**Precondition**: `isRunActive && activeJob` — Cancel button is visible.

```typescript
const handleCancel = useCallback(async () => {
  if (!activeJob) return;
  setCancelling(true);
  try {
    await jobsApi.cancel(activeJob.id);       // POST /api/jobs/{id}/cancel
    // Optimistic: set local job status to "cancelled"
    setActiveJob((prev) => prev ? { ...prev, status: 'cancelled' } : prev);
    // Optimistic: set local run status to "CANCELLED"
    setRun((prev) => prev ? { ...prev, status: 'CANCELLED' as any } : prev);
  } catch (e: any) {
    setError(e.message);
  } finally {
    setCancelling(false);
  }
}, [activeJob]);
```

**Sequence**:
1. Sets `cancelling = true` (button shows "Cancelling...")
2. Calls `jobsApi.cancel(activeJob.id)` → `POST /api/jobs/{id}/cancel`
3. On success:
   - `setActiveJob({ ...prev, status: 'cancelled' })` — polling loop will see terminal
   - `setRun({ ...prev, status: 'CANCELLED' })` — `isRunActive` becomes false
4. Sets `cancelling = false`

**UI effect of optimistic update**:
- `isRunActive` becomes `false` (because `run.status` is now "CANCELLED")
- Status badge: "Cancelled"
- CancelledBanner appears
- Cancel button disappears
- Delete button enables
- Elapsed timer stops

#### From RunCard in RunList (`RunCard.tsx`, line 37-48)

```typescript
async function handleCancel() {
  if (!run.job_id) return;
  setCancellingCard(true);
  try {
    await jobsApi.cancel(run.job_id);
    onStatusChange?.();   // Triggers parent loadRuns() for immediate re-fetch
  } catch {
    // Cancel failed silently — polling will show real status
  } finally {
    setCancellingCard(false);
  }
}
```

**Key difference from RunDetail**: No optimistic local state update. Instead, calls `onStatusChange()` which triggers `loadRuns()` in RunList to re-fetch all runs from the API. The re-fetched data reflects the DB state of the eval_run (which may or may not be "cancelled" yet).

### Phase B: API Client

`jobsApi.cancel()` (`src/services/api/jobsApi.ts`, line 38-40):

```typescript
async cancel(jobId: string): Promise<void> {
  await apiRequest(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
}
```

Simple POST, no request body. Returns void — the response body is ignored.

### Phase C: Backend — Cancel Route

`POST /api/jobs/{job_id}/cancel` (`backend/app/routes/jobs.py`, line 54-74):

```python
@router.post("/{job_id}/cancel")
async def cancel_job(job_id: UUID, db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    # Guard: cannot cancel completed/failed jobs
    if job.status in ("completed", "failed"):
        raise HTTPException(400, f"Cannot cancel job in '{job.status}' state")

    # Guard: already cancelled — early return, SKIP eval_run update
    if job.status == "cancelled":
        return {"id": str(job_id), "status": "cancelled"}

    now = datetime.now(timezone.utc)
    job.status = "cancelled"
    job.completed_at = now

    # Attempt to cancel associated eval_run in same transaction
    await db.execute(
        update(EvalRun)
        .where(EvalRun.job_id == job_id, EvalRun.status == "running")
        .values(status="cancelled", completed_at=now)
    )
    await db.commit()
    return {"id": str(job_id), "status": "cancelled"}
```

**Status transition logic**:

| Current job.status | Action | HTTP Response |
|---|---|---|
| `queued` | Cancel job + eval_run | 200 `{"id": ..., "status": "cancelled"}` |
| `running` | Cancel job + eval_run | 200 `{"id": ..., "status": "cancelled"}` |
| `cancelled` | Early return, **SKIP eval_run update** | 200 `{"id": ..., "status": "cancelled"}` |
| `completed` | Reject | 400 `"Cannot cancel job in 'completed' state"` |
| `failed` | Reject | 400 `"Cannot cancel job in 'failed' state"` |

**DB writes** (single transaction):

| Table | Operation | Condition |
|---|---|---|
| `jobs` | UPDATE `status='cancelled', completed_at=now` | Always (for queued/running) |
| `eval_runs` | UPDATE `status='cancelled', completed_at=now` | WHERE `job_id=X AND status='running'` |

### Phase D: Backend — Worker Cooperative Cancellation

The worker detects cancellation via `is_job_cancelled()` checks placed at the start of each thread/test iteration.

#### Batch runner (`batch_runner.py`, line 217-221)

```python
for i, thread_id in enumerate(ids_to_evaluate, 1):
    if await is_job_cancelled(job_id):
        raise JobCancelledError("Job was cancelled by user")
    # ... LLM calls for this thread (could take 30s-2min each) ...
```

#### Adversarial runner (`adversarial_runner.py`, line 151-153, 179)

```python
async def check_cancelled():
    if await is_job_cancelled(job_id):
        raise JobCancelledError("Job was cancelled by user")

for i, tc in enumerate(cases, 1):
    await check_cancelled()
    # ... conversation + judge (could take 30s-5min per case) ...
```

#### `is_job_cancelled()` (`job_worker.py`, line 84-88)

```python
async def is_job_cancelled(job_id) -> bool:
    async with async_session() as db:
        job = await db.get(Job, job_id)
        return job is not None and job.status == "cancelled"
```

Opens a FRESH session each time (no stale reads). Reads the committed job status from DB.

#### `JobCancelledError` handlers

**Batch** (`batch_runner.py`, line 404-423):
```python
except JobCancelledError:
    duration = time.monotonic() - start_time
    summary = {"total_threads": total, "completed": ..., "errors": ..., "cancelled": True}
    async with async_session() as db:
        await db.execute(
            update(EvalRun).where(EvalRun.id == run_id).values(
                status="cancelled", completed_at=now, duration_ms=..., summary=summary
            )
        )
        await db.commit()
    return {"run_id": str(run_id), "cancelled": True}
```

**Adversarial** (`adversarial_runner.py`, line 272-286): Same pattern.

#### Worker loop post-processing (`job_worker.py`, line 117-127)

After `process_job()` returns (including from `JobCancelledError` handler):
```python
result_data = await process_job(job.id, job.job_type, job.params)
await db.refresh(job)
if job.status == "cancelled":
    logger.info("Job was cancelled during execution, skipping completed update")
else:
    job.status = "completed"
    ...
```

The worker correctly checks for cancellation and does NOT overwrite the job status.

### Phase E: Frontend — Polling Loop Reaction

The RunDetail polling loop (`RunDetail.tsx`, line 295-354) was already running before cancel:

```typescript
// In the polling while loop:
const job = await jobsApi.get(runJobId!);    // GET /api/jobs/{id}
setActiveJob(job);
// ... fetch incremental threads/adversarial ...

if (["completed", "failed", "cancelled"].includes(job.status)) {
    // Terminal — final fetch
    const r = await fetchRun(runId);           // GET /api/eval-runs/{id}
    setRun(r);                                 // Uses eval_run status, not job status
    break;
}
```

**After cancel**:
1. Optimistic update already set `run.status = 'CANCELLED'` → `isRunActive = false` → polling effect won't re-trigger
2. If polling was mid-cycle when cancel happened, it continues and the next `jobsApi.get()` returns `status: "cancelled"` → breaks

**But**: If the user navigated TO the page AFTER cancelling (page refresh), the polling starts fresh:
1. Initial load fetches eval_run → `status: "running"` (if orphaned)
2. Polling starts → fetches job → `status: "cancelled"` (terminal)
3. Final fetch: `fetchRun()` → still `status: "running"` (orphaned!)
4. `setRun(r)` with `status: "running"` → `isRunActive` stays `true`
5. Polling breaks, `pollingRef.current = false`
6. **The polling useEffect does NOT re-trigger** because deps `[runJobId, runStatus, runId]` haven't changed
7. Page permanently stuck in active state

### Phase F: JobCompletionWatcher Reaction

If the job was being tracked in `useJobTrackerStore` (i.e., user submitted this job in the current browser session and hasn't navigated to RunDetail yet):

1. `JobCompletionWatcher` polls `GET /api/jobs/{id}` every 3s
2. Detects `status: "cancelled"` → terminal
3. Shows warning toast: `"{label} was cancelled"`
4. Calls `untrackJob(jobId)` — removes from tracker

If user IS on RunDetail for this run, the mount effect already called `untrackJob()`, so the watcher won't fire a duplicate toast.

---

## Cancellation Timing & Race Conditions

### Timeline: Successful Cancel (job cfb1b6b1)

```
T+0:00    Job started, eval_run created (status=running)
T+8:36    Cancel route fires:
          → job.status = "cancelled", job.completed_at set
          → UPDATE eval_runs SET status='cancelled' ← SUCCEEDS
          → Commit (both in one transaction)
T+8:36+   Worker is mid-LLM-call (thread 2 of 25)
T+14:14   Worker's LLM call finishes
          → is_job_cancelled() returns True
          → JobCancelledError raised
          → Handler: UPDATE eval_runs SET status='cancelled', completed_at
            (overwrites cancel route's completed_at with later timestamp)
          → Returns to worker_loop
          → Worker sees job.status == "cancelled", skips completed update
```

**DB evidence**: `run.completed_at` is 5m38s AFTER `job.completed_at`, proving the `JobCancelledError` handler ran second and overwrote the cancel route's timestamp.

### Timeline: Failed Cancel (job 34971418)

```
T+0:00    Job started, eval_run created (status=running)
T+3:26    Thread 3 completed (last saved thread_evaluation)
T+3:27    Worker enters thread 4 iteration
          → is_job_cancelled() returns False (job still running)
          → progress_callback("Evaluating thread 4/10")
          → LLM calls begin...
T+8:13    Cancel route fires:
          → job.status = "cancelled"
          → UPDATE eval_runs SET status='cancelled' WHERE status='running'
          → Commit
T+8:13+   Worker's LLM call for thread 4 still in progress...
          [PROCESS CRASH / RESTART / TIMEOUT — worker never returns to check]
```

**DB evidence**: `eval_run.status = "running"`, `eval_run.completed_at = NULL`. The cancel route's UPDATE *should* have set it to "cancelled", yet it remains "running".

**Possible explanations**:
1. **Docker restart**: If the container restarted after the cancel commit, `recover_stale_jobs()` only recovers JOBS, not eval_runs. The orphaned eval_run remains "running" forever.
2. **Transaction ordering**: The cancel route's UPDATE committed successfully, but the worker (in a separate session) may have been mid-flush with the eval_run loaded in its ORM session. A subsequent write from the worker's session could have reset the status. (Unlikely with raw `update()` statements, but possible with ORM session state.)
3. **The cancel route's UPDATE matched 0 rows**: If the eval_run's status had been briefly changed by a concurrent transaction (e.g., worker's batch_metadata update flushing stale ORM state), the WHERE clause `status='running'` could have not matched. But batch_metadata updates don't touch status.

**Most likely cause**: The Docker container was restarted between the cancel and the worker detecting it. The cancel route's UPDATE set eval_run to "cancelled", but the restart lost the in-memory worker state. On restart, `recover_stale_jobs()` found the JOB was already "cancelled" (not "running"), so it didn't touch it. And there is NO equivalent `recover_stale_eval_runs()` function.

---

## DB Tables Written During Cancel

| Step | Table | Operation | Key Fields |
|------|-------|-----------|------------|
| Cancel route | `jobs` | UPDATE | `status='cancelled', completed_at=now` |
| Cancel route | `eval_runs` | UPDATE | `status='cancelled', completed_at=now` (WHERE `job_id=X AND status='running'`) |
| Worker detects cancel | `eval_runs` | UPDATE | `status='cancelled', completed_at=now, duration_ms, summary` (WHERE `id=run_id`) |
| Worker loop post-process | — | SKIP | Worker sees `job.status == 'cancelled'`, does not update |

---

## Zustand Stores Involved

| Store | Usage in Flow |
|-------|---------------|
| `useJobTrackerStore` | `untrackJob()` fired by `JobCompletionWatcher` when it detects terminal job. RunDetail mount also untracks. |

Note: The cancel flow does NOT write to any Zustand store. `setActiveJob()` and `setRun()` are React local state in RunDetail, not global stores.

---

## API Sequence Diagrams

### Scenario A: Cancel from RunDetail (normal — both mechanisms work)

```
User clicks Cancel
    │
    ├── POST /api/jobs/{jobId}/cancel
    │       Backend:
    │       ├── job.status = "cancelled"
    │       ├── UPDATE eval_runs SET status='cancelled' WHERE job_id=X AND status='running'
    │       └── COMMIT (200 OK)
    │
    ├── [Optimistic] setRun(status='CANCELLED'), setActiveJob(status='cancelled')
    │       → isRunActive = false
    │       → Cancel button disappears
    │       → CancelledBanner shows
    │       → Delete button enables
    │
    └── Polling loop (if still running):
        └── GET /api/jobs/{jobId} → status: "cancelled" → TERMINAL
            ├── GET /api/eval-runs/{runId}/threads (incremental)
            ├── GET /api/eval-runs/{runId}/adversarial (incremental)
            └── GET /api/eval-runs/{runId} → status: "cancelled" ← MATCHES optimistic
                └── setRun(r) ← confirms optimistic update

Meanwhile, backend worker:
    ├── is_job_cancelled() → True at next iteration
    ├── JobCancelledError raised
    ├── Handler: UPDATE eval_runs SET status='cancelled', duration_ms, summary
    └── Returns to worker_loop → skips completed update
```

### Scenario B: Cancel from RunDetail (broken — eval_run orphaned)

```
User clicks Cancel
    │
    ├── POST /api/jobs/{jobId}/cancel → 200 OK
    │       (cancel route sets job AND eval_run to cancelled... or tries to)
    │
    ├── [Optimistic] UI shows "Cancelled"  ← Looks correct!
    │
    └── [Later: page refresh]
        │
        ├── GET /api/eval-runs/{runId} → status: "running"  ← ORPHANED!
        │   → isRunActive = true
        │   → Status badge: "Running"
        │   → Cancel button: visible
        │   → Delete button: disabled
        │
        ├── Polling starts
        │   └── GET /api/jobs/{jobId} → status: "cancelled" → TERMINAL
        │       └── GET /api/eval-runs/{runId} → status: "running"  ← STILL ORPHANED
        │           → setRun(r) → isRunActive stays true
        │           → Polling stops but page stays stuck
        │
        └── User clicks Cancel again
            ├── POST /api/jobs/{jobId}/cancel → 200
            │   (early return: job already cancelled, SKIPS eval_run update)
            ├── [Optimistic] UI shows "Cancelled" again
            └── [Page refresh] → reverts to "Running" again. Infinite loop.
```

### Scenario C: Cancel from RunList

```
User clicks "Stop run" on RunCard
    │
    ├── POST /api/jobs/{jobId}/cancel → 200 OK
    │
    ├── onStatusChange() → loadRuns()
    │   ├── GET /api/eval-runs?app_id=kaira-bot&...
    │   └── Returns eval_run with status from DB
    │       ├── If "cancelled": RunCard shows cancelled, no cancel button
    │       └── If "running" (orphaned): RunCard shows running, cancel button still visible
    │
    └── RunList polling (every 5s if any run is "running"):
        └── Continues indefinitely if orphaned eval_run exists
```

---

## Bugs & Issues Found

### BUG 1: Double-Cancel Skips Eval Run Update (Idempotency Failure)

**Severity: HIGH — makes orphaned eval_runs unfixable via UI**

The cancel route (line 62-63) returns early for already-cancelled jobs:
```python
if job.status == "cancelled":
    return {"id": str(job_id), "status": "cancelled"}
```

This skips the `update(EvalRun)` statement. So if the first cancel failed to update the eval_run (orphaned), every subsequent cancel attempt also fails to fix it.

**Verified via Playwright**: Called `POST /api/jobs/34971418.../cancel` — returned `200 {"status": "cancelled"}`. The eval_run remained `status='running'` in DB.

### BUG 2: No Recovery Mechanism for Orphaned Eval Runs

**Severity: HIGH — orphaned runs persist forever**

`recover_stale_jobs()` (called on startup) only recovers `jobs` table entries stuck in "running". It does NOT check or recover `eval_runs` stuck in "running" whose associated job is already terminal.

```python
# recover_stale_jobs only touches Job table
result = await db.execute(
    select(Job).where(
        and_(Job.status == "running", Job.started_at < cutoff)
    )
)
```

There is no equivalent `recover_stale_eval_runs()`.

### BUG 3: Optimistic Cancel Update Is Not Durable

**Severity: MEDIUM — confusing UX on page refresh**

The RunDetail `handleCancel` sets `run.status = 'CANCELLED'` in local React state. This immediately fixes the UI. But:
- The value only lives in React state (not persisted)
- Page refresh re-fetches from DB → gets stale "running" status
- The user sees "Cancelled" → refreshes → sees "Running" → confused

The fix should be on the backend (ensure eval_run is actually updated), but the frontend should also reconcile: if `job.status === 'cancelled'` but `eval_run.status === 'running'`, treat the run as cancelled.

### BUG 4: Cancel Button Visible But Misleading on Orphaned Runs

**Severity: MEDIUM — clicking Cancel succeeds but doesn't fix anything**

For an orphaned run:
1. `isRunActive = true` (eval_run says "running")
2. `activeJob` is set from polling (job status: "cancelled")
3. Cancel button renders (needs `isRunActive && activeJob`)
4. User clicks Cancel → `POST /api/jobs/{id}/cancel` → 200 (early return)
5. Optimistic update shows "Cancelled"
6. Refresh → back to "Running"

The button gives false hope. It succeeds at the API level but doesn't fix the orphaned eval_run.

### BUG 5: Cancel During LLM Call Has Unbounded Latency

**Severity: LOW — expected but worth noting**

`is_job_cancelled()` is only checked at the START of each thread/test iteration. If an LLM call takes 2 minutes (e.g., large thread + slow model), the user waits up to 2 minutes before the worker detects cancellation. During this time:
- Job is "cancelled" in DB
- Eval_run may or may not be "cancelled" (cancel route's UPDATE)
- Worker is blocked on LLM I/O
- Frontend shows optimistic "Cancelled" (or polling detects cancelled job)

There's no mechanism to interrupt the in-flight LLM call itself.

### BUG 6: RunList Re-fetch After Cancel May Show Stale Eval Run

**Severity: LOW — usually self-corrects via polling**

`RunCard.handleCancel()` calls `onStatusChange()` → `loadRuns()` immediately after the cancel API returns. But the `loadRuns()` fetches eval_runs from DB. If the cancel route's eval_run UPDATE and the `loadRuns()` fetch happen near-simultaneously, the fetch might read the pre-cancel state (depending on PostgreSQL transaction ordering). The 5-second polling in RunList will eventually show the correct state.

---

## State Management Summary

| State Variable | Source | Role in Cancel Flow |
|---|---|---|
| `cancelling` (RunDetail) | Set during cancel API call | Disables Cancel button during request |
| `cancellingCard` (RunCard) | Set during cancel API call | Disables "Stop run" button during request |
| `activeJob` (RunDetail) | Optimistically updated to `status: 'cancelled'` | Polling loop sees terminal, breaks |
| `run` (RunDetail) | Optimistically updated to `status: 'CANCELLED'` | `isRunActive` becomes false, UI updates |
| `isRunActive` (RunDetail, derived) | `run.status.toLowerCase() === "running"` | Controls cancel/delete buttons, banners, timer |
| `pollingRef` (RunDetail) | Ref to prevent duplicate loops | Polling stops on terminal detection |

---

## Error Handling

| Error Source | Handling |
|---|---|
| `POST /cancel` network error | RunDetail: `setError(e.message)` → full-page error banner |
| `POST /cancel` returns 400 (completed/failed job) | RunDetail: `setError(e.message)` → error banner. RunCard: silently caught |
| `POST /cancel` returns 404 (job not found) | Same as 400 handling |
| Worker `JobCancelledError` | Caught in runner → sets eval_run to cancelled → returns to worker_loop |
| Worker crash during cancel processing | Job stays "cancelled" (correct). Eval_run may stay "running" (orphaned) |

---

## Verified via Playwright

| Test | Result |
|---|---|
| Navigate to orphaned run `eed28526` | Shows "Running", Cancel visible, Delete disabled, timer at 45m+ |
| Click Cancel on orphaned run | Optimistic update → "Cancelled", CancelledBanner, Delete enabled |
| Page refresh after cancel | Reverts to "Running", Cancel visible, Delete disabled |
| `POST /cancel` on already-cancelled job (API) | Returns 200 `{"status": "cancelled"}`, eval_run unchanged |
| `POST /cancel` on completed job (API) | Returns 400 `"Cannot cancel job in 'completed' state"` |
| Network requests on RunDetail for orphaned run | Polling fetches job → cancelled (terminal) → re-fetches eval_run → still "running" → stops polling, but isRunActive stays true |
