# Flow 2: Viewing RunDetail for a Running Job

## Summary

User lands on RunDetail page → 3 parallel API calls fetch run metadata, thread evaluations, and adversarial evaluations → if run status is "running" and has a `job_id`, a polling loop starts that fetches job progress + incremental results every 2s → on job terminal state, polling stops, final run data is re-fetched, and appropriate banners are shown.

**Critical finding**: The page derives `isRunActive` from the **eval_run** status, not the job status. If the eval_run is orphaned in "running" (job already cancelled), the page remains stuck in an active state forever.

---

## Step-by-Step Trace

### Phase A: Initial Data Load

**Entry**: `RunDetail` component mounts with `runId` from URL params.

**useEffect (line 263-282)**: Fires on mount, makes 3 parallel requests:

| Request | Endpoint | Purpose |
|---------|----------|---------|
| `fetchRun(runId)` | `GET /api/eval-runs/{runId}` | Run metadata (status, summary, config) |
| `fetchRunThreads(runId)` | `GET /api/eval-runs/{runId}/threads` | Thread evaluation results |
| `fetchRunAdversarial(runId)` | `GET /api/eval-runs/{runId}/adversarial` | Adversarial test results |

Both thread and adversarial fetches have `.catch(() => ({ evaluations: [] }))` so a 404 or error on one doesn't block the others.

**State set on success**:
- `setRun(r)` — the full run object (drives `isRunActive`, header, banners)
- `setThreadEvals(t.evaluations)` — thread result rows for the table
- `setAdversarialEvals(a.evaluations)` — adversarial result rows

**Backend SQL**:
- `GET /api/eval-runs/{runId}`: `db.get(EvalRun, run_id)` → single row lookup by PK
- `GET /api/eval-runs/{runId}/threads`: `select(ThreadEvaluation).where(run_id == ...)` → all thread rows for this run
- `GET /api/eval-runs/{runId}/adversarial`: `select(AdversarialEvaluation).where(run_id == ...)` → all adversarial rows

**Verified via Playwright**: All 3 calls return 200 and render correctly for both completed and running runs.

### Phase B: Untrack from Global Watcher

**useEffect (line 285-290)**: On mount, checks if this run's `runId` is in `useJobTrackerStore.activeJobs`. If found, calls `untrackJob(jobId)` to prevent `JobCompletionWatcher` from firing duplicate toasts.

This runs via `getState()` (not a selector), so it's a one-time check, not reactive.

### Phase C: Polling Loop for Active Runs

**Trigger condition (line 295-296)**: `runJobId` exists AND `runStatus.toLowerCase() === "running"`.

**Guard (line 297-298)**: `pollingRef.current` prevents duplicate loops if the effect re-fires.

**Poll cycle (line 302-345)**:

```
while (!cancelled) {
  1. GET /api/jobs/{jobId}         → setActiveJob(job)
  2. GET /api/eval-runs/{runId}/threads      → setThreadEvals
     GET /api/eval-runs/{runId}/adversarial  → setAdversarialEvals
  3. If job.status is terminal (completed/failed/cancelled):
     a. GET /api/eval-runs/{runId}  → setRun (final state)
     b. If completed: show success banner for 8s
     c. Break
  4. Sleep 2000ms
}
pollingRef.current = false
```

**useEffect deps**: `[runJobId, runStatus, runId]` — only re-triggers if these change.

### Phase D: isRunActive Drives the UI

The single boolean `isRunActive` (line 226) controls almost everything:

```typescript
const isRunActive = run != null && run.status.toLowerCase() === "running";
```

| Feature | When `isRunActive = true` | When `isRunActive = false` |
|---------|--------------------------|---------------------------|
| Progress bar | Shown (if `activeJob` exists) | Hidden |
| Elapsed timer | Ticking | Shows final duration |
| Cancel button | Visible | Hidden |
| Delete button | Disabled | Enabled |
| Success/failure banners | Hidden | Shown based on status |
| "Evaluations being processed" placeholder | Shown (if no results yet) | Shows "No evaluations found" empty state |

### Phase E: RunList Interaction

`RunList` (line 109-121) also checks for running runs:
```typescript
const hasRunning = [...runs, ...customRuns].some(r => r.status === 'running');
```
If ANY run is "running", RunList polls every 5s via `loadRuns()`.

**RunCard** (line 28): `const isActive = run.status.toLowerCase() === "running"` — shows cancel button, disables delete.

---

## Bugs & Issues Found

### BUG 1: Orphaned "Running" Eval Run Causes Infinite Active State

**Severity: HIGH — UI permanently stuck, blocks delete, wastes API calls**

When an eval_run is orphaned in "running" status (job already cancelled but eval_run not updated — see Flow 1 Bug #3), the following cascade happens:

1. **RunDetail page** loads the eval_run with `status: "running"` → `isRunActive = true`
2. **Polling loop** starts (because `runStatus === "running"` and `runJobId` exists)
3. **First poll**: `GET /api/jobs/{jobId}` returns `status: "cancelled"` (terminal)
4. **Polling fetches final run data**: `GET /api/eval-runs/{runId}` → returns `status: "running"` (still orphaned!)
5. **Polling breaks** (job is terminal) and sets `pollingRef.current = false`
6. **But `run.status` is still "running"** → `isRunActive` stays `true`
7. **The polling `useEffect` does NOT re-trigger** because none of its deps `[runJobId, runStatus, runId]` changed
8. **Result**: Page permanently shows:
   - Status badge: "Running"
   - Cancel button visible (clicking it succeeds but only optimistically)
   - Delete button disabled
   - Elapsed timer counting up forever (37+ minutes observed)
   - No success/failure/cancelled banner

**Verified via Playwright**: Navigated to `eed28526` (orphaned running eval_run). Page shows "Running", elapsed timer at 36m+, Cancel visible, Delete disabled. After poll detected job cancelled, no state change occurred.

**DB evidence**:
```
eval_run eed28526 | status=running | job_id=34971418
job 34971418      | status=cancelled
```

### BUG 2: Polling Detects Terminal Job But Doesn't Reconcile Eval Run Status

**Severity: HIGH — root cause of Bug #1's persistence in UI**

When the polling loop detects a terminal job state (line 325-339), it re-fetches the eval_run:

```typescript
if (["completed", "failed", "cancelled"].includes(job.status)) {
  const r = await fetchRun(runId);
  setRun(r);  // <-- This uses the eval_run status, not the job status
  break;
}
```

The code trusts that the eval_run status will match the job's terminal status. When they disagree (orphaned eval_run), the UI shows the eval_run's stale status. The polling loop does NOT reconcile the two — it doesn't check "if job is cancelled but eval_run is still running, treat it as cancelled."

### BUG 3: Cancel on Already-Cancelled Job Skips Eval Run Update

**Severity: MEDIUM — makes it impossible to fix orphaned eval_runs via UI**

The cancel endpoint (`jobs.py` line 62-63) returns early for already-cancelled jobs:
```python
if job.status == "cancelled":
    return {"id": str(job_id), "status": "cancelled"}
```

This skips the `update(EvalRun)` statement (line 68-72). So if the eval_run was missed during the original cancel, clicking Cancel again in the UI will NOT fix it.

**Verified via Playwright**: Clicked Cancel on the orphaned run. API returned 200 (early return path). Optimistic UI showed "Cancelled". But `eval_runs` table still shows `status=running`. Page refresh reverts to "Running".

### BUG 4: RunList Polls Forever Due to Orphaned Running Eval Run

**Severity: MEDIUM — performance impact**

`RunList` starts a 5-second polling interval whenever any run has `status === "running"` (line 117-121). The orphaned eval_run triggers this indefinitely, causing repeated `fetchRuns()` and `fetchEvalRuns()` calls every 5 seconds on the runs list page, even when no actual work is happening.

**Verified via Playwright**: RunList shows `eed28526` as "Running" with a "Stop run" button.

### BUG 5: Thread Error Messages Are Empty Strings

**Severity: LOW — poor UX for error diagnosis**

Thread evaluations that failed during the batch (e.g., LLM timeout) are saved with `result={"error": error_msg}` (batch_runner.py line 349). However, the observed DB data shows:

```sql
SELECT result->'error' FROM thread_evaluations WHERE run_id='eed28526' AND success_status=false;
-- Result: ""  (empty string for both failed threads)
```

The error message `str(e)` was empty. This is likely because the exception was raised during cancellation handling — the `JobCancelledError` at line 220 propagates up, but some threads may have been partially processed and caught by the per-thread `except` (line 334) with an empty exception message.

The ThreadDetailCard component (line 896-901) does handle empty errors:
```tsx
{result?.error && (
  <div>
    <strong>Evaluation failed:</strong> {result.error || "Unknown error (timeout or internal failure)"}
  </div>
)}
```

But `""` is falsy in JS, so `result?.error` evaluates to `""` which is falsy → the error banner is NOT shown at all. The thread appears with 0 messages, N/A verdicts, and no explanation.

### BUG 6: No Progress Bar for Orphaned Running Runs

**Severity: LOW — misleading UI**

The progress bar component `RunProgressBar` (line 60-143) is only rendered when `isRunActive` is true AND `activeJob` exists:

```tsx
{isRunActive && <RunProgressBar job={activeJob} elapsed={elapsed} />}
```

On initial page load, `activeJob` is `null`. It only gets set when the polling loop fetches the job. For the orphaned run:
1. Polling starts, fetches job (sets `activeJob` to the cancelled job)
2. `RunProgressBar` checks `job.status` — cancelled means it returns `null` (line 81)
3. So even though `isRunActive` is true, the progress bar is not shown

This means the user sees the "Running" status badge but no progress bar — a confusing mixed signal.

---

## API Sequence Diagram

### Normal Flow (Run is truly running, completes)

```
RunDetail mounts
    │
    ├── GET /api/eval-runs/{runId}            → status: "running", job_id: "xxx"
    ├── GET /api/eval-runs/{runId}/threads    → { evaluations: [] }  (none yet)
    └── GET /api/eval-runs/{runId}/adversarial → { evaluations: [] }
    │
    │  isRunActive = true, polling starts
    │
    ├── [Poll 1] GET /api/jobs/{jobId}         → status: "running", progress: {current: 2, total: 10}
    │   ├── GET /api/eval-runs/{runId}/threads → { evaluations: [2 rows] }
    │   └── GET /api/eval-runs/{runId}/adversarial → (empty)
    │
    ├── [Poll 2] GET /api/jobs/{jobId}         → status: "running", progress: {current: 5, total: 10}
    │   ├── GET /api/eval-runs/{runId}/threads → { evaluations: [5 rows] }
    │   └── GET /api/eval-runs/{runId}/adversarial → (empty)
    │
    ├── [Poll N] GET /api/jobs/{jobId}         → status: "completed"  ← TERMINAL
    │   ├── GET /api/eval-runs/{runId}/threads → { evaluations: [10 rows] }
    │   ├── GET /api/eval-runs/{runId}/adversarial → (empty)
    │   └── GET /api/eval-runs/{runId}         → status: "completed", summary: {...}
    │
    └── isRunActive = false, success banner shown, delete enabled
```

### Orphaned Flow (Eval run stuck in "running", job cancelled)

```
RunDetail mounts
    │
    ├── GET /api/eval-runs/{runId}            → status: "running", job_id: "xxx"
    ├── GET /api/eval-runs/{runId}/threads    → { evaluations: [3 rows] }  (partial)
    └── GET /api/eval-runs/{runId}/adversarial → { evaluations: [] }
    │
    │  isRunActive = true, polling starts
    │
    ├── [Poll 1] GET /api/jobs/{jobId}         → status: "cancelled"  ← TERMINAL
    │   ├── GET /api/eval-runs/{runId}/threads → { evaluations: [3 rows] }
    │   ├── GET /api/eval-runs/{runId}/adversarial → (empty)
    │   └── GET /api/eval-runs/{runId}         → status: "running"  ← STILL ORPHANED!
    │
    └── Polling stops, but isRunActive remains true
        → Status badge: "Running" (wrong)
        → Cancel button: visible (misleading)
        → Delete button: disabled (can't clean up)
        → Elapsed timer: counting forever
```

---

## DB Tables Read During Viewing

| Step | Table | Query | Key Fields Returned |
|------|-------|-------|---------------------|
| Initial load | `eval_runs` | `db.get(EvalRun, run_id)` | status, summary, job_id, started_at, completed_at, duration_ms, error_message, batch_metadata |
| Initial load | `thread_evaluations` | `select(...).where(run_id == ...)` | thread_id, intent_accuracy, worst_correctness, efficiency_verdict, success_status, result (JSONB) |
| Initial load | `adversarial_evaluations` | `select(...).where(run_id == ...)` | category, difficulty, verdict, goal_achieved, total_turns, result (JSONB) |
| Poll cycle | `jobs` | `db.get(Job, job_id)` | status, progress (JSONB), started_at, error_message |
| Poll cycle | `thread_evaluations` | Same as initial | Incremental: more rows as threads complete |
| Poll cycle | `adversarial_evaluations` | Same as initial | Incremental: more rows as tests complete |
| Final fetch | `eval_runs` | Same as initial | Final status, summary, duration_ms |

---

## Zustand Stores Involved

| Store | Usage in Flow |
|-------|---------------|
| `useJobTrackerStore` | `untrackJob()` on mount to prevent duplicate toasts from `JobCompletionWatcher` |

Note: Unlike submission flow, RunDetail does NOT use the job tracker for polling — it has its own independent polling loop driven by local React state.

---

## State Management Summary

| State Variable | Source | Drives |
|----------------|--------|--------|
| `run` | `fetchRun()` response | `isRunActive`, header, banners, metadata display |
| `threadEvals` | `fetchRunThreads()` response | Table/detail view, distribution charts, stat pills |
| `adversarialEvals` | `fetchRunAdversarial()` response | Adversarial section |
| `activeJob` | `jobsApi.get()` from polling | Progress bar, cancel button handler, elapsed time source |
| `showSuccessBanner` | Set true on completed detection | Success banner (auto-hides after 8s) |
| `cancelling` | Set true during cancel API call | Cancel button disabled state |
| `pollingRef` | Ref to prevent duplicate loops | Guard for polling useEffect |

---

## Error Handling

| Error Source | Handling |
|-------------|----------|
| `fetchRun()` fails on initial load | `setError(e.message)` → renders error banner, no further content |
| `fetchRunThreads()` fails on initial load | Caught silently → `{ evaluations: [] }`, other data still loads |
| `fetchRunAdversarial()` fails on initial load | Caught silently → `{ evaluations: [] }`, other data still loads |
| `jobsApi.get()` fails in polling | Caught silently → continues polling (wait and retry) |
| Incremental thread/adversarial fetch fails in polling | Caught silently → continues polling |
| `fetchRun()` fails on final fetch | Caught silently → polling stops anyway |
| Cancel API fails | `setError(e.message)` → renders error banner |
| Delete API fails | `setError(e.message)` → renders error banner |

**Note**: Once `setError` is called, the entire page renders as an error banner (line 391-397) with no way to recover except browser refresh.
