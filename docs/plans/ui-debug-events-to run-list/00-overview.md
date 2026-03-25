# Job Lifecycle UX Audit — Overview

## Problem Statement

The post-submit UX for evaluation jobs is broken. Specific symptoms:

1. **Cancel does not persist**: User cancels a running job, UI optimistically shows "cancelled", but on page refresh the run still shows "Running" status.
2. **Run detail shows stale data**: After submitting a batch eval and navigating to run detail, the page doesn't reflect the submitted job without a manual browser refresh.
3. **Thread errors show blank**: When a thread evaluation fails (e.g., LLM timeout), the thread row in run detail shows no useful information — no error message.
4. **400 on double-cancel**: Clicking cancel on an already-cancelled job returns HTTP 400.

These are symptoms of a deeper issue: the job/eval_run lifecycle is not properly wired end-to-end. Before fixing anything, we need to trace every flow and understand the full picture.

## Architecture Context

- **Frontend**: React 19 + Vite + Zustand stores (TypeScript)
- **Backend**: FastAPI + async SQLAlchemy + asyncpg (Python)
- **Database**: PostgreSQL 16
- **Dev proxy**: Vite `/api/*` → FastAPI `localhost:8721`

### Key DB Tables

| Table | Purpose |
|-------|---------|
| `jobs` | Background job queue (status: queued/running/completed/failed/cancelled) |
| `eval_runs` | Evaluation run results (status: running/completed/completed_with_errors/failed/cancelled) |
| `thread_evaluations` | Per-thread results within a batch eval run |
| `adversarial_evaluations` | Per-test results within an adversarial eval run |
| `api_logs` | LLM API call logs per run |

### Key Relationship

- `eval_runs.job_id` → `jobs.id` (an eval_run is created BY a job)
- `thread_evaluations.run_id` → `eval_runs.id`
- `adversarial_evaluations.run_id` → `eval_runs.id`
- `api_logs.run_id` → `eval_runs.id`

### Key Backend Files

| File | Purpose |
|------|---------|
| `backend/app/routes/jobs.py` | Jobs API: submit, list, get, cancel |
| `backend/app/routes/eval_runs.py` | Eval runs API: list, get, threads, adversarial, delete |
| `backend/app/services/job_worker.py` | Background worker loop + job handlers |
| `backend/app/services/evaluators/batch_runner.py` | Batch evaluation orchestrator |
| `backend/app/services/evaluators/adversarial_runner.py` | Adversarial evaluation orchestrator |
| `backend/app/services/evaluators/custom_evaluator_runner.py` | Custom evaluator runner |
| `backend/app/services/evaluators/voice_rx_runner.py` | Voice-RX evaluation runner |
| `backend/app/services/evaluators/llm_base.py` | LLM provider interface + timeout handling |
| `backend/app/models/job.py` | Job SQLAlchemy model |
| `backend/app/models/eval_run.py` | EvalRun, ThreadEvaluation, AdversarialEvaluation, ApiLog models |

### Key Frontend Files

| File | Purpose |
|------|---------|
| `src/features/evalRuns/pages/RunDetail.tsx` | Run detail page (shows job progress, thread results, cancel/delete) |
| `src/features/evalRuns/pages/RunList.tsx` | Run list page |
| `src/features/evalRuns/components/RunCard.tsx` | Individual run card in list |
| `src/features/evalRuns/components/RunRowCard.tsx` | Row-style run card UI |
| `src/features/evalRuns/components/EvalTable.tsx` | Thread evaluation table view |
| `src/features/evalRuns/components/NewBatchEvalOverlay.tsx` | Batch eval submission wizard |
| `src/features/evalRuns/components/NewAdversarialOverlay.tsx` | Adversarial test submission wizard |
| `src/hooks/useSubmitAndRedirect.ts` | Shared hook: submit job → poll for run_id → redirect |
| `src/services/api/jobsApi.ts` | Jobs API client (submit, get, cancel) |
| `src/services/api/evalRunsApi.ts` | Eval runs API client |
| `src/services/api/jobPolling.ts` | submitAndPollJob utility |
| `src/stores/jobTrackerStore.ts` | Global in-flight job tracking (Zustand) |
| `src/components/JobCompletionWatcher.tsx` | Headless component: polls tracked jobs, fires toasts |
| `src/config/routes.ts` | Route path constants |
| `src/types/evalRuns.ts` | TypeScript types for eval runs, thread results |

### Key Frontend Stores

| Store | Purpose |
|-------|---------|
| `useJobTrackerStore` | Tracks active jobs globally (sessionStorage) |
| `useLLMSettingsStore` | LLM provider/model/key settings |
| `useGlobalSettingsStore` | Global settings including timeouts |
| `useTaskQueueStore` | Task progress queue for inline evaluations |

## Flows to Investigate

Each flow gets its own file. Investigation must cover:
- **UI**: What the user sees, what components render, what state drives the render
- **APIs**: Exact endpoints called, request/response shapes, sequence
- **DB**: Which tables are read/written, what status transitions happen
- **State**: Zustand stores, React state, polling loops, optimistic updates
- **Errors**: How errors are caught, propagated, and surfaced to the user

### Flow 1: Job Submission (`docs/plans/01-flow-submission.md`)
User clicks "Start Evaluation" in overlay → job created → worker picks it up → eval_run created → redirect to RunDetail.

### Flow 2: Viewing RunDetail for a Running Job (`docs/plans/02-flow-viewing.md`)
User lands on RunDetail → initial data load → polling loop → incremental thread results → completion detection → final state.

### Flow 3: User Cancels a Running Job (`docs/plans/03-flow-cancel.md`)
User clicks Cancel → API call → DB updates → UI reaction → worker detects cancellation → eval_run status update.

### Flow 4: Cancel Then Refresh Page (`docs/plans/04-flow-cancel-refresh.md`)
After cancel, user refreshes browser → what APIs fire → what DB state is read → what renders → WHY it still shows "Running".

### Flow 5: User Deletes a Run (`docs/plans/05-flow-delete.md`)
User clicks Delete → confirmation → API call → DB cascade → navigation.

### Error Handling Audit (`docs/plans/06-error-handling.md`)
Error factory? Error propagation chain? How backend errors reach the user? Toast vs inline vs silent?

### Gap Analysis (`docs/plans/07-gap-analysis.md`)
What SHOULD happen vs what ACTUALLY happens. Root causes. Fix plan.

## Progress Tracker

| Flow | Status | File |
|------|--------|------|
| Flow 1: Submission | DONE | `01-flow-submission.md` |
| Flow 2: Viewing | DONE | `02-flow-viewing.md` |
| Flow 3: Cancel | DONE | `03-flow-cancel.md` |
| Flow 4: Cancel+Refresh | DONE | `04-flow-cancel-refresh.md` |
| Flow 5: Delete | DONE | `05-flow-delete.md` |
| Error Audit | DONE | `06-error-handling.md` |
| Gap Analysis | DONE | `07-gap-analysis.md` |

## Rules

1. **Do NOT write any code** until all 7 files are complete and reviewed by user.
2. **Do NOT assume anything works.** Verify by reading code, querying DB, and hitting APIs via Playwright.
3. **Write findings to the flow file immediately** so progress is saved if session runs out of tokens.
4. **Stop after completing each flow.** Let user initiate the next flow in a new session if needed.
5. **Use Playwright MCP** to observe actual API responses and UI state where useful.
6. **Use `docker exec evals-postgres psql`** to query actual DB state.
