# Flow 4: Cancel Then Refresh Page

## Summary

After cancelling a running job, the user refreshes the browser. The fresh page load fetches the eval_run from DB, which still shows `status: "running"` (orphaned). The polling loop starts, detects the job is "cancelled" (terminal), does a final eval_run fetch — still "running" — and stops. The page is permanently stuck showing "Running" with a ticking elapsed timer, a Cancel button that does nothing useful, and a disabled Delete button. This is an unrecoverable dead end from the UI.

**Core issue**: The page trusts `eval_run.status` as the source of truth for `isRunActive`, but when the eval_run is orphaned (status "running" while job is "cancelled"), there's no reconciliation between the two statuses.

---

## Step-by-Step Trace

### Phase A: Fresh Page Load — Initial Data Fetch

When the browser navigates to `/kaira/runs/{runId}`, the `RunDetail` component mounts:

#### 1. Initial data load effect (`RunDetail.tsx`, line 263-282)

```typescript
useEffect(() => {
  if (!runId) return;
  let cancelled = false;
  Promise.all([
    fetchRun(runId),                    // GET /api/eval-runs/{runId}
    fetchRunThreads(runId).catch(...),   // GET /api/eval-runs/{runId}/threads
    fetchRunAdversarial(runId).catch(...), // GET /api/eval-runs/{runId}/adversarial
  ]).then(([r, t, a]) => {
    if (!cancelled) {
      setRun(r);          // Sets run with status from DB
      setThreadEvals(t.evaluations);
      setAdversarialEvals(a.evaluations);
    }
  });
}, [runId]);
```

**API calls fired** (verified via Playwright network log):
| # | Request | Response |
|---|---------|----------|
| 1 | `GET /api/eval-runs/eed28526...` | 200 — `status: "running"`, `completedAt: null`, `summary: null` |
| 2 | `GET /api/eval-runs/eed28526.../threads` | 200 — 3 thread evaluations (partial results) |
| 3 | `GET /api/eval-runs/eed28526.../adversarial` | 200 — 0 adversarial evaluations |

**State after initial fetch**:
- `run.status = "running"`
- `run.job_id = "34971418-..."` (the cancelled job)
- `run.summary = null` (no summary — worker never completed)
- `run.completed_at = null`
- `isRunActive = true` (derived: `run.status.toLowerCase() === "running"`)
- `activeJob = null` (not yet fetched)

#### 2. Job tracker untrack effect (`RunDetail.tsx`, line 285-290)

```typescript
useEffect(() => {
  if (!runId) return;
  const { activeJobs, untrackJob } = useJobTrackerStore.getState();
  const match = activeJobs.find((j) => j.runId === runId);
  if (match) untrackJob(match.jobId);
}, [runId]);
```

On a fresh page load (hard refresh), `sessionStorage` is cleared (new tab) or may still have the job tracked (same tab, SPA navigation). If the job IS tracked, it gets untracked here to prevent `JobCompletionWatcher` from firing duplicate toasts.

**For a hard refresh**: `sessionStorage` is preserved within the same tab, so the job may still be tracked. The untrack call removes it.

**For a new tab / incognito**: `sessionStorage` is empty, so no match found.

### Phase B: Polling Loop Starts

#### 3. Poll job progress effect (`RunDetail.tsx`, line 295-354)

**Trigger**: `runStatus` changed to "running" and `runJobId` is now set.

```typescript
useEffect(() => {
  if (!runJobId || !runStatus || runStatus.toLowerCase() !== "running") return;
  if (pollingRef.current) return;
  pollingRef.current = true;

  async function poll() {
    while (!cancelled) {
      const job = await jobsApi.get(runJobId!);    // GET /api/jobs/{jobId}
      setActiveJob(job);                            // Sets activeJob state

      // Fetch incremental results
      const [t, a] = await Promise.all([
        fetchRunThreads(runId),
        fetchRunAdversarial(runId),
      ]);
      setThreadEvals(t.evaluations);
      setAdversarialEvals(a.evaluations);

      if (["completed", "failed", "cancelled"].includes(job.status)) {
        // Terminal — final fetch
        const r = await fetchRun(runId);
        setRun(r);                                  // ← THIS IS THE CRITICAL LINE
        break;
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
    pollingRef.current = false;
  }
  poll();
}, [runJobId, runStatus, runId]);
```

**API calls fired** (verified via Playwright):
| # | Request | Response |
|---|---------|----------|
| 4 | `GET /api/jobs/34971418...` | 200 — `status: "cancelled"`, `progress: {current: 4, total: 10, message: "Evaluating thread 4/10"}` |
| 5 | `GET /api/eval-runs/eed28526.../threads` | 200 — 3 thread evaluations (same as initial) |
| 6 | `GET /api/eval-runs/eed28526.../adversarial` | 200 — 0 adversarial evaluations |
| 7 | `GET /api/eval-runs/eed28526...` | 200 — `status: "running"` (**STILL ORPHANED**) |

**Sequence of state changes during polling**:

1. `setActiveJob(job)` → `activeJob = { status: "cancelled", ... }`
   - `RunProgressBar` receives `activeJob` with `isCancelled = true` → returns `null` (hides)
   - Cancel button condition: `isRunActive && activeJob` → `true && truthy` → **renders Cancel button**
   - But `activeJob.status === "cancelled"` — the cancel button is misleading

2. `job.status === "cancelled"` → terminal → enter final fetch branch

3. `setRun(r)` with `r.status = "running"` → **`isRunActive` stays `true`**
   - No CancelledBanner (run.status is not "cancelled")
   - No SuccessBanner
   - Delete button stays disabled (`isRunActive` is true)
   - Elapsed timer keeps ticking

4. `break` — exits polling loop, `pollingRef.current = false`

### Phase C: Final Rendered State After Polling Settles

**Verified via Playwright snapshot after 3-second wait**:

| UI Element | State | Why |
|---|---|---|
| Status badge | "Running" | `run.status = "running"` |
| Cancel button | **Visible** | `isRunActive (true) && activeJob (not null)` |
| Delete button | Disabled | `isRunActive` is true |
| Delete tooltip | "Cannot delete a running evaluation. Cancel it first." | Hardcoded in JSX |
| Progress bar | Hidden | `RunProgressBar` returns null when `activeJob.status === "cancelled"` |
| Elapsed timer | Ticking (51m+ and counting) | `useElapsedTime(startedAt, active=true)` |
| CancelledBanner | Not shown | `run.status.toLowerCase() !== "cancelled"` |
| Thread results | 3 of 10 shown | Partial results from before worker crashed |
| Polling | **Stopped** | Loop exited after detecting terminal job |

### Phase D: User Clicks Cancel (Double-Cancel)

**Verified via Playwright** — clicking the visible Cancel button:

1. `handleCancel()` fires → `POST /api/jobs/34971418.../cancel`
2. Backend sees `job.status == "cancelled"` → early return (line 62-63 of `jobs.py`):
   ```python
   if job.status == "cancelled":
       return {"id": str(job_id), "status": "cancelled"}
   ```
   **The `update(EvalRun)` statement is SKIPPED** — eval_run remains "running".
3. Frontend receives 200 → optimistic update:
   - `setActiveJob({ ...prev, status: 'cancelled' })` — already was cancelled
   - `setRun({ ...prev, status: 'CANCELLED' })` — UI switches to "Cancelled"
4. CancelledBanner appears, Cancel button hides, Delete enables, timer shows "<1s"
5. **But this is only in React state** — not persisted to DB.

### Phase E: Second Refresh — Infinite Loop

Refreshing again restarts the entire cycle from Phase A:
1. Fetch eval_run → `status: "running"` (unchanged in DB)
2. Polling starts → job "cancelled" → final fetch → run still "running"
3. Page stuck in "Running" again
4. User can click Cancel → optimistic "Cancelled" → refresh → "Running"
5. **Infinite loop. No escape via UI.**

---

## RunList Behavior for Orphaned Runs

**Verified via Playwright**: RunList shows the orphaned run as:
- Status badge: "Running"
- "Stop run" button: visible (because `isActive` = `run.status.toLowerCase() === "running"`)
- Delete button: disabled with tooltip "Stop the run before deleting"

### RunList polling behavior

```typescript
const hasRunning = useMemo(
  () => [...runs, ...customRuns].some((r) => {
    const status = 'status' in r ? r.status : '';
    return status === 'running';
  }),
  [runs, customRuns],
);

useEffect(() => {
  if (!hasRunning) return;
  const interval = setInterval(() => loadRuns(), 5000);
  return () => clearInterval(interval);
}, [hasRunning, loadRuns]);
```

Since the orphaned eval_run's status is "running", `hasRunning` is always `true`. The RunList polls every 5 seconds **indefinitely**. This is wasted network traffic that never stops because the eval_run status never changes.

### RunCard cancel behavior

Clicking "Stop run" on RunCard (line 37-48 of `RunCard.tsx`):
1. `jobsApi.cancel(run.job_id)` → 200 (early return, skips eval_run update)
2. `onStatusChange?.()` → `loadRuns()` re-fetches all runs
3. Re-fetched data still shows `status: "running"` for the orphaned run
4. RunCard still shows "Running" with "Stop run" button
5. **Same dead end as RunDetail**

---

## Delete Endpoint — Dead End for Orphaned Runs

**Verified via curl**: `DELETE /api/eval-runs/eed28526...` returns:
```json
{"detail": "Cannot delete a running evaluation. Cancel it first."}
```

The delete route (`eval_runs.py`, line 250-260) guards against deleting running evals:
```python
if run.status == "running":
    raise HTTPException(400, "Cannot delete a running evaluation. Cancel it first.")
```

Since the eval_run is stuck in "running" and the cancel route can't fix it (early return), the run is **undeletable via the UI or API**.

---

## JobCompletionWatcher Behavior on Refresh

The `JobCompletionWatcher` (`JobCompletionWatcher.tsx`) is mounted at the app root. On refresh:

1. `useJobTrackerStore` persists to `sessionStorage` — survives same-tab refresh
2. If the job was tracked in a previous navigation:
   - Watcher polls `GET /api/jobs/{jobId}` → status "cancelled" (terminal)
   - Checks if user is on RunDetail for this run → yes → suppresses toast
   - Calls `untrackJob(jobId)` — removes from tracker
3. If the job was NOT tracked (new tab, or already untracked):
   - Watcher has nothing to poll
   - No effect on the orphaned run

**Key point**: The watcher only fires toasts and untracks jobs. It does NOT fix the eval_run status. Even if it detects the job is cancelled, it has no mechanism to update the eval_run.

---

## DB Evidence

### Orphaned eval_run

```sql
SELECT id, status, completed_at, summary, error_message
FROM eval_runs WHERE id = 'eed28526-4d30-4ef5-85b3-48de23172977';
```

| id | status | completed_at | summary | error_message |
|---|---|---|---|---|
| eed28526... | running | NULL | NULL | NULL |

### Associated cancelled job

```sql
SELECT id, status, completed_at, progress
FROM jobs WHERE id = '34971418-259a-44e2-b939-3a21f932236c';
```

| id | status | completed_at | progress |
|---|---|---|---|
| 34971418... | cancelled | 2026-02-18 11:56:46.754897+00 | `{current: 4, total: 10, message: "Evaluating thread 4/10"}` |

### Thread evaluations (partial)

```sql
SELECT count(*) FROM thread_evaluations
WHERE run_id = 'eed28526-4d30-4ef5-85b3-48de23172977';
-- Result: 3 (out of 10 planned)
```

---

## State Management Summary

### After Fresh Page Load + Polling Settles

| State Variable | Value | Source |
|---|---|---|
| `run` | `{ status: "running", job_id: "34971418...", completedAt: null, summary: null }` | `GET /api/eval-runs/{id}` (DB) |
| `activeJob` | `{ status: "cancelled", progress: {current: 4, total: 10} }` | `GET /api/jobs/{id}` (DB) |
| `isRunActive` | `true` | Derived: `run.status.toLowerCase() === "running"` |
| `pollingRef.current` | `false` | Set after polling loop exits |
| `threadEvals` | 3 items | `GET /api/eval-runs/{id}/threads` |
| `adversarialEvals` | 0 items | `GET /api/eval-runs/{id}/adversarial` |
| `cancelling` | `false` | Not actively cancelling |
| `elapsed` | Ticking | `useElapsedTime(startedAt, active=true)` |

### Contradictory State

The fundamental problem: **`run.status` and `activeJob.status` disagree**.

| Signal | Value | Interpretation |
|---|---|---|
| `eval_run.status` | `"running"` | Run is active |
| `job.status` | `"cancelled"` | Job is terminal |
| Frontend `isRunActive` | `true` | Based on eval_run only |
| Frontend Cancel button | Visible | Based on `isRunActive && activeJob` |
| Frontend Delete button | Disabled | Based on `isRunActive` |
| Progress bar | Hidden | Based on `activeJob.status === "cancelled"` |

The progress bar correctly uses the job status (hides itself), but every other UI element uses the eval_run status (incorrectly shows "Running").

---

## Bugs & Issues Specific to This Flow

### BUG 1: No Job-vs-Run Status Reconciliation on Final Fetch

**Severity: HIGH — root cause of the stuck "Running" page**

When the polling loop detects a terminal job and does the final `fetchRun()`, it unconditionally sets the run data:
```typescript
const r = await fetchRun(runId);
if (!cancelled) setRun(r);
```

There's no reconciliation check like:
```typescript
// Missing: if job is cancelled but run is still "running", treat as cancelled
if (job.status === 'cancelled' && r.status === 'running') {
  r.status = 'cancelled';  // Frontend reconciliation
}
```

The frontend blindly trusts the eval_run status, even when the job status contradicts it.

### BUG 2: Polling Stops But Page Stays "Active" Forever

**Severity: HIGH — page is permanently stuck**

After the polling loop breaks (job is terminal), `pollingRef.current = false`. The polling useEffect dependencies are `[runJobId, runStatus, runId]`. Since `runStatus` didn't change (still "running"), the effect doesn't re-trigger. The page is stuck with:
- `isRunActive = true` (timer ticking, cancel visible, delete disabled)
- No polling running (loop exited)
- No mechanism to ever resolve the status

### BUG 3: Cancel Button Is Visible But Futile

**Severity: MEDIUM — gives false hope**

After polling settles, the Cancel button appears because `isRunActive && activeJob` is true. But clicking it triggers the early-return path on the backend (job already cancelled), which doesn't update the eval_run. The optimistic update looks correct but evaporates on refresh.

### BUG 4: Elapsed Timer Ticks Forever

**Severity: LOW — cosmetic but confusing**

`useElapsedTime(startedAt, active=true)` increments every second. Since `isRunActive` never becomes false, the timer shows ever-increasing values (50m, 51m, 52m...) even though nothing is running.

### BUG 5: RunList Polls Indefinitely for Orphaned Runs

**Severity: MEDIUM — wasted resources**

RunList's `hasRunning` check includes the orphaned eval_run, so it polls every 5 seconds forever. Each poll fetches all eval_runs but the orphaned one never changes status.

### BUG 6: Orphaned Run Cannot Be Deleted

**Severity: HIGH — no cleanup path**

The delete route rejects runs with `status: "running"`. The cancel route can't fix the status (early return). The only way to clean up is direct DB access:
```sql
UPDATE eval_runs SET status = 'cancelled', completed_at = NOW()
WHERE id = 'eed28526-4d30-4ef5-85b3-48de23172977';
```

This is a dead end for users without DB access.

---

## API Sequence Diagram

### Full Flow: Cancel → Refresh → Stuck

```
[SESSION 1: User cancels]
    POST /api/jobs/{jobId}/cancel → 200 (job + eval_run set to cancelled)
    [Optimistic] UI shows "Cancelled" ✓

    [Later: worker crash / restart]
    eval_run status reverts or was never updated
    Job stays cancelled (correct)

[SESSION 2: User refreshes browser]
    │
    ├── GET /api/eval-runs/{runId}
    │   → 200: { status: "running", job_id: "...", completedAt: null }
    │   → setRun(r) → isRunActive = true
    │   → UI: Status="Running", no progress bar, no banners
    │
    ├── GET /api/eval-runs/{runId}/threads → 200: 3 partial results
    │
    ├── GET /api/eval-runs/{runId}/adversarial → 200: 0 results
    │
    ├── [Polling starts: runStatus="running", runJobId set]
    │   └── GET /api/jobs/{jobId}
    │       → 200: { status: "cancelled" }
    │       → setActiveJob(job) → Cancel button appears
    │       → Terminal! →
    │           ├── GET /api/eval-runs/{runId}/threads → 200: same 3
    │           ├── GET /api/eval-runs/{runId}/adversarial → 200: same 0
    │           └── GET /api/eval-runs/{runId}
    │               → 200: { status: "running" } ← STILL ORPHANED
    │               → setRun(r) → isRunActive STILL true
    │               → break (polling stops)
    │
    └── [Page state: PERMANENTLY STUCK]
        → Status: "Running" (wrong)
        → Timer: ticking (wrong)
        → Cancel: visible but futile
        → Delete: disabled (no cleanup)
        → Polling: stopped (won't retry)

[USER ACTION: Clicks Cancel]
    POST /api/jobs/{jobId}/cancel → 200 (early return, SKIPS eval_run)
    [Optimistic] UI shows "Cancelled"
    [Refresh] → Back to "Running" → INFINITE LOOP
```

### RunList View

```
[Page load]
    GET /api/eval-runs?limit=100 → includes orphaned run with status "running"
    hasRunning = true → polling every 5s

[Every 5 seconds]
    GET /api/eval-runs?limit=100 → orphaned run STILL "running"
    GET /api/eval-runs?app_id=kaira-bot&eval_type=custom&limit=200
    → Infinite polling loop

[User clicks "Stop run" on RunCard]
    POST /api/jobs/{jobId}/cancel → 200 (early return)
    onStatusChange() → loadRuns() → re-fetches → still "running"
    → No change
```

---

## Verified via Playwright

| Test | Result |
|---|---|
| Navigate to orphaned run detail after hard refresh | Status="Running", timer ticking, Delete disabled |
| Wait for polling to settle (~3s) | Cancel button appears, progress bar hidden |
| Network: initial load APIs | 3 calls: eval-run, threads, adversarial |
| Network: polling APIs | job GET → cancelled → threads + adversarial + eval-run (still running) |
| Click Cancel on orphaned run | Optimistic: "Cancelled", CancelledBanner, Delete enabled |
| Network: cancel POST | `POST /cancel` → 200 OK |
| DB: eval_run after double-cancel | Still `status='running'`, `completed_at=NULL` |
| Hard refresh after cancel | Reverts to "Running", timer ticking, Delete disabled |
| RunList page view | Orphaned run shows "Running", "Stop run" visible, Delete disabled |
| RunList: hasRunning polling | Polls every 5s indefinitely |
| `DELETE /api/eval-runs/{id}` via curl | 400: "Cannot delete a running evaluation. Cancel it first." |
| Elapsed timer after 3s wait | Shows 51m+, continuously incrementing |
