# Flow 1: Job Submission

## Summary

User clicks "Start Evaluation" in overlay → job created in DB (status=queued) → registered in global job tracker store → success toast → poll for `run_id` in job progress → redirect to RunDetail (or fallback to RunList).

Meanwhile, backend worker picks up job → marks running → handler creates `eval_run` → writes `run_id` to job progress → processes evaluations → finalizes eval_run and job.

---

## Step-by-Step Trace

### Phase A: Frontend — Wizard Submission

**Entry points:**
- `NewBatchEvalOverlay` (`src/features/evalRuns/components/NewBatchEvalOverlay.tsx`)
- `NewAdversarialOverlay` (`src/features/evalRuns/components/NewAdversarialOverlay.tsx`)

Both overlays use the shared `useSubmitAndRedirect` hook (`src/hooks/useSubmitAndRedirect.ts`).

**Wizard `handleSubmit` callback** (batch example, line 136-174):
1. Reads CSV file content into a string (`uploadedFile.text()`)
2. Reads timeout settings from `useGlobalSettingsStore`
3. Calls `submitJob('evaluate-batch', { ...params })` (from `useSubmitAndRedirect`)

**`useSubmitAndRedirect.submit(jobType, params)`** (line 28-81):
1. Sets `isSubmitting = true`
2. Calls `jobsApi.submit(jobType, params)` → `POST /api/jobs` with `{ jobType, params }`
3. On success, registers job in `useJobTrackerStore.trackJob({ jobId, appId, jobType, label, trackedAt })`
4. Shows success toast via `notificationService.success()`
5. **Polls for `run_id`** (up to 10s, every 2s):
   - Calls `jobsApi.get(job.id)` → `GET /api/jobs/{jobId}`
   - Extracts `run_id` from `job.progress.run_id`
   - If found: calls `useJobTrackerStore.resolveRunId(jobId, runId)`, navigates to `routes.kaira.runDetail(runId)`
   - If job reaches terminal state (completed/failed/cancelled): breaks
   - On API error: breaks
6. If no redirect happened, navigates to `fallbackRoute` (runs list)
7. Calls `onClose()` to dismiss overlay
8. On any error: shows error toast, does NOT navigate

### Phase B: Backend — Job Creation

**`POST /api/jobs`** (`backend/app/routes/jobs.py`, line 17-27):
1. Receives `JobCreate` schema: `{ jobType, params, status="queued", progress={current:0, total:0, message:""} }`
2. Creates `Job` model instance
3. Commits to DB
4. Returns `JobResponse` (201 Created)

**DB state after creation:**
| Field | Value |
|-------|-------|
| `id` | new UUID |
| `job_type` | `"evaluate-batch"` or `"evaluate-adversarial"` |
| `status` | `"queued"` |
| `params` | Full params dict (includes CSV content, LLM config, timeouts) |
| `progress` | `{"current": 0, "total": 0, "message": ""}` |
| `started_at` | NULL |
| `completed_at` | NULL |

### Phase C: Backend — Worker Picks Up Job

**`worker_loop()`** (`backend/app/services/job_worker.py`, line 91-157):
1. Polls every 5 seconds for oldest `status="queued"` job
2. Sets `job.status = "running"`, `job.started_at = now()`
3. Commits
4. Calls `process_job(job.id, job.job_type, job.params)` → dispatches to registered handler

### Phase D: Backend — Handler Creates EvalRun

#### Batch Handler (`backend/app/services/evaluators/batch_runner.py`)

1. **Creates EvalRun** (line 103-123):
   ```python
   EvalRun(id=run_id, app_id="kaira-bot", eval_type="batch_thread",
           job_id=job_id, status="running", started_at=now(), ...)
   ```
2. **Writes `run_id` to job progress** (line 126-133):
   ```python
   update(Job).where(Job.id == job_id).values(
       progress={"current": 0, "total": 0, "message": "Initializing...", "run_id": str(run_id)}
   )
   ```
3. Resolves API key from settings
4. Loads CSV data, resolves thread IDs
5. Updates EvalRun with resolved details (total_items, model, etc.)
6. Creates LLM provider

#### Adversarial Handler (`backend/app/services/evaluators/adversarial_runner.py`)

Same pattern: creates EvalRun (line 80-98), writes `run_id` to progress (line 101-110).

### Phase E: Backend — Processing Loop

**Batch:** For each thread ID:
1. Checks `is_job_cancelled(job_id)` → raises `JobCancelledError` if cancelled
2. Calls `progress_callback(job_id, i, total, message)` → **`update_job_progress()`**
3. Runs intent/correctness/efficiency evaluators
4. Saves `ThreadEvaluation` row
5. Calls `progress_callback` again after thread

**Adversarial:** For each test case:
1. Checks cancelled
2. Calls local `report_progress()` which preserves `run_id` in progress
3. Generates test case, runs conversation, judges transcript
4. Saves `AdversarialEvaluation` row

### Phase F: Backend — Finalization

1. Computes final status: `completed`, `completed_with_errors`, or `failed`
2. Updates EvalRun: `status`, `completed_at`, `duration_ms`, `summary`
3. Returns result dict to worker loop
4. Worker loop (line 117-127): refreshes job, checks if cancelled, otherwise sets `job.status = "completed"`, `job.progress = {"current": 1, "total": 1, "message": "Done"}`

### Phase G: Frontend — Global Watcher

**`JobCompletionWatcher`** (`src/components/JobCompletionWatcher.tsx`):
- Mounted in `MainLayout` (always active)
- Polls every 3s for each tracked job in `useJobTrackerStore`
- On terminal state: shows toast (success/failure/cancelled), calls `untrackJob`
- Suppresses toast if user is already on that run's detail page

**`RunDetail`** (`src/features/evalRuns/pages/RunDetail.tsx`):
- On mount, untracks the job from global watcher (prevents duplicate toasts)
- If run is "running", starts its own polling loop (every 2s):
  - Fetches job via `GET /api/jobs/{jobId}`
  - Fetches threads/adversarial results incrementally
  - On terminal state: fetches final run data, shows success banner

---

## Bugs & Issues Found

### BUG 1: `run_id` Lost from Job Progress (Batch Runner)

**Severity: HIGH — causes redirect failure**

The batch runner writes `run_id` to job progress at line 128-133:
```python
progress={"current": 0, "total": 0, "message": "Initializing...", "run_id": str(run_id)}
```

But `update_job_progress()` (job_worker.py line 73-81) **overwrites the entire JSON**:
```python
progress={"current": current, "total": total, "message": message}
```

The first `progress_callback` call in the batch loop (line 223) destroys `run_id`. This means the frontend's 10-second polling window in `useSubmitAndRedirect` has a **very narrow race window** to catch `run_id`:
- Worker picks up job: 0-5 seconds after submission
- Batch runner writes `run_id`: milliseconds after pickup
- First `progress_callback` (overwrites `run_id`): after data loading + LLM setup (varies, could be 1-10s)
- Frontend polls: every 2 seconds, starting ~2s after submission

**DB evidence:** All recent jobs have progress WITHOUT `run_id`:
```
34971418 | cancelled | {"current": 4, "total": 10, "message": "Evaluating thread 4/10"}
cfb1b6b1 | cancelled | {"current": 2, "total": 25, "message": "Evaluating thread 2/25"}
734e1bc6 | completed | {"current": 1, "total": 1, "message": "Done"}
```

The worker loop's completion handler (line 125) also overwrites without `run_id`:
```python
job.progress = {"current": 1, "total": 1, "message": "Done"}
```

### BUG 2: Inconsistent Progress Key Between Runners

**Severity: MEDIUM**

| Runner | Progress key for run ID | Preserved across updates? |
|--------|------------------------|--------------------------|
| `batch_runner` | `run_id` | NO — lost after first progress_callback |
| `adversarial_runner` | `run_id` | YES — local `report_progress` includes it |
| `voice_rx_runner` | `eval_run_id` | YES (different key!) |
| `custom_evaluator_runner` | `eval_run_id` | YES (different key!) |

`useSubmitAndRedirect` only looks for `progress.run_id` (line 52-53). Voice-RX and custom runners use `eval_run_id`, so the redirect will NEVER work for those job types.

### BUG 3: Eval Run Orphaned in "Running" Status After Cancel

**Severity: HIGH — causes stale data on page refresh**

DB evidence:
```
job 34971418 | status=cancelled | eval_run eed28526 | status=running  ← BROKEN
job cfb1b6b1 | status=cancelled | eval_run 958d9878 | status=cancelled ← OK
```

The cancel route (`jobs.py` line 54-74) does attempt to update the eval_run:
```python
await db.execute(
    update(EvalRun)
    .where(EvalRun.job_id == job_id, EvalRun.status == "running")
    .values(status="cancelled", completed_at=now)
)
```

But the eval_run for job `34971418` is STILL "running". Possible causes:
1. Worker crashed/restarted between cancel and `JobCancelledError` handler
2. Cancel route fired but eval_run wasn't committed yet (race with worker creating it)
3. The `recover_stale_jobs()` function only recovers JOBS, not eval_runs — so orphaned eval_runs remain "running" forever

### BUG 4: CSV Content Stored in Job Params

**Severity: LOW (performance)**

The entire CSV content is stored in `job.params.csv_content` as a string. The API response for `GET /api/jobs/{id}` returns the full params including CSV content (1.8MB+ in observed responses). This makes every poll request in `useSubmitAndRedirect` and `JobCompletionWatcher` transfer the full CSV on every cycle.

### Observation: Fallback Redirect Works Reliably

When `run_id` is NOT found in progress within 10s, `useSubmitAndRedirect` falls back to navigating to the runs list page (`routes.kaira.runs`). This is the most common path given Bug #1. Users see the run in the list and can click into it manually.

---

## Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│ FRONTEND                                                         │
│                                                                  │
│  NewBatchEvalOverlay                                             │
│       │ handleSubmit()                                           │
│       ▼                                                          │
│  useSubmitAndRedirect.submit(jobType, params)                    │
│       │                                                          │
│       ├─── POST /api/jobs ──────────────────────────► [Backend]  │
│       │         ◄──── Job { id, status:"queued" }                │
│       │                                                          │
│       ├─── trackJob(jobId) ──► useJobTrackerStore                │
│       │                                                          │
│       ├─── notificationService.success()                         │
│       │                                                          │
│       ├─── [Poll loop: 2s interval, 10s max]                    │
│       │    GET /api/jobs/{id}                                    │
│       │    Look for progress.run_id                              │
│       │    ├── Found? → navigate(/kaira/runs/{runId})            │
│       │    └── Terminal? → break                                 │
│       │                                                          │
│       └─── [Fallback] → navigate(/kaira/runs)                   │
│                                                                  │
│  JobCompletionWatcher (global, parallel)                         │
│       │ Polls every 3s for tracked jobs                          │
│       └── Terminal → toast + untrackJob                          │
│                                                                  │
│  RunDetail (if redirected)                                       │
│       │ On mount: untrack from global watcher                    │
│       │ If running: poll job + threads/adversarial every 2s      │
│       └── On complete: fetch final run data, success banner      │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ BACKEND                                                          │
│                                                                  │
│  POST /api/jobs                                                  │
│       │ Create Job(status=queued)                                │
│       │ Commit + return                                          │
│       ▼                                                          │
│  worker_loop() [polls every 5s]                                  │
│       │ Find oldest queued job                                   │
│       │ Set status=running, started_at=now                       │
│       ▼                                                          │
│  process_job() → dispatch to handler                             │
│       │                                                          │
│       ▼                                                          │
│  run_batch_evaluation()                                          │
│       │                                                          │
│       ├── Create EvalRun(status=running, job_id=...)             │
│       ├── Write run_id to job.progress ← BUG: overwritten later │
│       ├── Load data, resolve threads                             │
│       │                                                          │
│       ├── [For each thread]                                      │
│       │   ├── Check is_job_cancelled()                           │
│       │   ├── progress_callback() ← OVERWRITES run_id in prog   │
│       │   ├── Run evaluators (intent, correctness, efficiency)   │
│       │   ├── Save ThreadEvaluation row                          │
│       │   └── progress_callback() again                          │
│       │                                                          │
│       └── Finalize: update EvalRun(status, summary, duration)    │
│                                                                  │
│  worker_loop() resumes:                                          │
│       │ Refresh job                                              │
│       │ If not cancelled: job.status=completed                   │
│       │ job.progress = {current:1, total:1, message:"Done"}      │
│       └── ← Also loses run_id                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## DB Tables Written During Submission

| Step | Table | Operation | Key Fields |
|------|-------|-----------|------------|
| Submit | `jobs` | INSERT | status=queued, params=full config |
| Worker pickup | `jobs` | UPDATE | status=running, started_at |
| Handler start | `eval_runs` | INSERT | status=running, job_id, eval_type |
| Handler start | `jobs` | UPDATE | progress.run_id (briefly) |
| Each thread | `jobs` | UPDATE | progress (current/total/message) |
| Each thread | `thread_evaluations` | INSERT | run_id, thread_id, results |
| Each thread | `api_logs` | INSERT (via LoggingLLMWrapper) | run_id, provider, model, prompt, response |
| Finalize | `eval_runs` | UPDATE | status, completed_at, duration_ms, summary |
| Worker done | `jobs` | UPDATE | status=completed, result, progress |

---

## Zustand Stores Involved

| Store | Usage in Flow |
|-------|---------------|
| `useJobTrackerStore` | `trackJob()` after submit, `resolveRunId()` if run_id found, `untrackJob()` on RunDetail mount or watcher terminal |
| `useLLMSettingsStore` | Read provider/model for default values in wizard |
| `useGlobalSettingsStore` | Read timeout settings for params |
| `useAppSettingsStore` | Read Kaira API settings for adversarial wizard |

---

## Error Handling

| Error Source | Handling |
|-------------|----------|
| `POST /api/jobs` fails | `useSubmitAndRedirect` catch → `notificationService.error()`, no navigation |
| Poll `GET /api/jobs/{id}` fails | Catch in poll loop → `break` (stops polling), falls through to fallback navigate |
| Worker handler throws | `worker_loop` catch → `job.status = "failed"`, `job.error_message = str(e)[:2000]` |
| Handler creates EvalRun then throws | EvalRun stays in DB (good!), handler's own except block marks `eval_run.status = "failed"` |
| LLM call fails for one thread | Caught per-thread, saves error ThreadEvaluation, increments `results_summary["errors"]` |
