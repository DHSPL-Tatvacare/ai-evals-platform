# Job Queue System — Current State Analysis

## Architecture

```
Frontend                    Backend                     DB
┌──────────────┐           ┌──────────────────┐        ┌──────────┐
│ jobsApi      │──POST────→│ /api/jobs        │───────→│ jobs     │
│  .submit()   │           │  creates row     │        │ table    │
│  .get()      │←─GET──────│  status=queued   │        └──────────┘
│  .cancel()   │           └──────────────────┘              ↑
└──────────────┘                                             │
                           ┌──────────────────┐              │
                           │ worker_loop()    │──poll 5s────→│
                           │  SEQUENTIAL      │              │
                           │  1 job at a time │              │
                           │  asyncio task    │              │
                           └──────────────────┘
```

## Job Status Lifecycle

```
QUEUED ──→ RUNNING ──→ COMPLETED
                   ├──→ FAILED
                   └──→ CANCELLED
```

## Registered Job Handlers (7 total)

| Handler | Job Type | Typical Duration | Concurrency Within |
|---------|----------|-----------------|-------------------|
| handle_evaluate_batch | evaluate-batch | 5-30 min | Yes (thread_workers) |
| handle_evaluate_adversarial | evaluate-adversarial | 10-60 min | Yes (case_workers) |
| handle_evaluate_voice_rx | evaluate-voice-rx | 1-5 min | No |
| handle_evaluate_custom | evaluate-custom | 30s-2 min | No |
| handle_evaluate_custom_batch | evaluate-custom-batch | 2-10 min | No |
| handle_generate_report | generate-report | 10-30s | No |
| handle_generate_cross_run_report | generate-cross-run-report | 10-30s | No |

## Critical Problems

### P1: Sequential Worker Blocks All Jobs
- `worker_loop()` does `await process_job(...)` — blocks until handler returns
- A stuck adversarial job (24h+) prevents ALL other jobs from running
- Report generation (10-30s) blocked by hour-long eval jobs

### P2: Stale Recovery Only on Startup
- `recover_stale_jobs()` only called in `main.py` lifespan startup
- If a job hangs mid-execution, no periodic recovery catches it
- Worker remains blocked until manual backend restart

### P3: No Job Priority
- FIFO queue only (ORDER BY created_at)
- Quick jobs (reports, custom evals) wait behind long-running ones
- No way to prioritize or categorize jobs

### P4: Frontend Missing "Queued" State Handling
- ReportTab: No handling of `cancelled` in `pollAndLoad` — UI stuck in "generating"
- No global queue position/wait indication
- JobCompletionWatcher only toasts on terminal states, not queue→running transitions

### P5: Silent Anthropic Failure in Report Narrative
- `report_service.py` catches RuntimeError from credential lookup
- Fallback only supports Gemini SA — Anthropic/OpenAI silently return None
- User sees report without narrative, no error explanation

## Key Files

| File | Purpose |
|------|---------|
| backend/app/services/job_worker.py | Worker loop, handlers, recovery |
| backend/app/routes/jobs.py | Jobs REST API |
| backend/app/models/job.py | Job ORM model |
| backend/app/main.py:41-46 | Worker startup |
| src/services/api/jobsApi.ts | Frontend jobs client |
| src/services/api/jobPolling.ts | Polling primitives |
| src/stores/jobTrackerStore.ts | Zustand job tracking (sessionStorage) |
| src/components/JobCompletionWatcher.tsx | Global background watcher |
| src/hooks/useSubmitAndRedirect.ts | Submit→track→redirect pattern |
| backend/app/services/reports/report_service.py | Report narrative with broken fallback |
| backend/app/services/evaluators/settings_helper.py | Credential resolution |
