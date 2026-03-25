# Runner Fixes Plan — Overview

**Created:** 2026-02-24
**Scope:** `backend/app/services/job_worker.py` and all 4 downstream runners
**Goal:** Fix crashes, cancellation chain corruption, and functional gaps across all 5 job types for both voice-rx and kaira-bot apps.

## Files In Scope

| File | Role |
|---|---|
| `backend/app/services/job_worker.py` | Job dispatch, worker loop, cancel cache, progress updates |
| `backend/app/services/evaluators/batch_runner.py` | `evaluate-batch` — kaira-bot thread evaluations |
| `backend/app/services/evaluators/adversarial_runner.py` | `evaluate-adversarial` — kaira-bot stress tests |
| `backend/app/services/evaluators/voice_rx_runner.py` | `evaluate-voice-rx` — voice-rx 3-step pipeline |
| `backend/app/services/evaluators/custom_evaluator_runner.py` | `evaluate-custom` + `evaluate-custom-batch` — both apps |
| `backend/app/services/evaluators/parallel_engine.py` | Shared concurrency engine used by batch + adversarial |
| `backend/app/services/evaluators/runner_utils.py` | Shared helpers: create_eval_run, finalize_eval_run, save_api_log |

## Files NOT In Scope (do not touch)

- `runner_utils.py` — `finalize_eval_run` is correct; the cancel-guard logic (`WHERE status != 'cancelled'`) is the reference pattern.
- `parallel_engine.py` — Correct. Cancellation propagation in `run_parallel` works (raises `JobCancelledError`, cancels remaining tasks).
- `settings_helper.py` — Correct. Auth resolution is thorough.
- All evaluator modules (`intent_evaluator.py`, `correctness_evaluator.py`, `efficiency_evaluator.py`, `adversarial_evaluator.py`) — Not part of this fix set.
- All frontend files — No changes.
- `job_worker.py` itself — The dispatch/loop/cancel-cache code is correct. Only the handler functions at the bottom are in scope (and only as the params-passing layer, not for logic changes).

## Job Types and App Coverage

| Job Type | Handler | Runner | App(s) | Affected by Phases |
|---|---|---|---|---|
| `evaluate-batch` | `handle_evaluate_batch` | `batch_runner.run_batch_evaluation` | kaira-bot | Phase 1 |
| `evaluate-adversarial` | `handle_evaluate_adversarial` | `adversarial_runner.run_adversarial_evaluation` | kaira-bot | Phase 1 |
| `evaluate-voice-rx` | `handle_evaluate_voice_rx` | `voice_rx_runner.run_voice_rx_evaluation` | voice-rx | Phase 1, Phase 2 |
| `evaluate-custom` | `handle_evaluate_custom` | `custom_evaluator_runner.run_custom_evaluator` | Both | Phase 1, Phase 2, Phase 3 |
| `evaluate-custom-batch` | `handle_evaluate_custom_batch` | `custom_evaluator_runner.run_custom_eval_batch` | Both | Phase 2 |

## All Bugs Found (Master List)

| ID | File | Lines | Severity | Apps | Phase | Summary |
|---|---|---|---|---|---|---|
| B1 | `batch_runner.py` | 580 shadows 170 | **CRASH** | kaira-bot | 1 | `from sqlalchemy import func, select` inside `except JobCancelledError` shadows module-level `select`. Python marks `select` as local for the entire function, so line 170 hits `UnboundLocalError`. Triggers when `skip_previously_processed=True`. |
| B2 | `batch_runner.py` | 560, 588 | Latent | kaira-bot | 1 | `from datetime import datetime, timezone` mid-function. Not imported at module level. Fragile — any future top-level `datetime` import creates same shadowing pattern as B1. |
| B3 | `adversarial_runner.py` | 150-151 | Latent | kaira-bot | 1 | `from sqlalchemy import update` + `from app.models.eval_run import EvalRun` mid-function. Module already imports from `app.models.eval_run` at line 28. Inconsistent. |
| B4 | `custom_evaluator_runner.py` | 242-244 | Latent | Both | 1 | `from sqlalchemy import update` + `from app.models.eval_run import EvalRun` mid-function in `run_custom_evaluator`. |
| B5 | `batch_runner.py` | 187 | Latent | kaira-bot | 1 | `import random` mid-function. |
| V1 | `voice_rx_runner.py` | 444-468 | **STATE CORRUPT** | voice-rx | 2 | `PipelineStepError` handler does direct DB update without cancel-guard. If cancel arrives between error and L454, failed status **overwrites** cancelled status. Should use `finalize_eval_run()` which has the guard. |
| M3 | `custom_evaluator_runner.py` | 302-309 | **CHAIN BREAK** | Both | 2 | `run_custom_evaluator` catches `JobCancelledError`, finalizes eval_run as cancelled, but **does not re-raise**. Returns normally with `status: "completed"`. Caller (`run_custom_eval_batch`) has no way to know cancellation occurred. Causes M1. |
| M1 | `custom_evaluator_runner.py` | 383 + 418-425 + 433 | **CHAIN BREAK** | Both | 2 | In `run_custom_eval_batch` parallel path: `_run_one` raises `JobCancelledError` outside its try/except. `gather(return_exceptions=True)` captures it as a value. Outer `except JobCancelledError` at L433 is dead code. Batch continues processing remaining evaluators after cancel, wasting LLM tokens. |
| M2 | `custom_evaluator_runner.py` | 269-280 | **FUNCTIONAL GAP** | Both | 3 | `thinking` param extracted at L219 but never passed to `llm.generate_with_audio()` or `llm.generate_json()`. User's thinking selection silently ignored. All other runners pass it correctly. |

## Phase Summary

| Phase | Goal | Risk Level | Files Changed |
|---|---|---|---|
| **Phase 1: Import Hygiene** | Fix B1 crash. Hoist all mid-function imports to top level across all 4 runners. Eliminate shadowing risk. | Low | `batch_runner.py`, `adversarial_runner.py`, `custom_evaluator_runner.py` |
| **Phase 2: Cancellation Chain** | Fix V1, M3, M1. Ensure cancel propagates correctly through every path for every job type for both apps. | Medium | `voice_rx_runner.py`, `custom_evaluator_runner.py` |
| **Phase 3: Functional Gaps** | Fix M2. Pass `thinking` param through custom evaluator LLM calls. | Low | `custom_evaluator_runner.py` |

## Invariants That Must Hold After All Phases

These are the contracts that the existing system relies on. Every fix must preserve them.

1. **EvalRun always created before work starts.** Every runner calls `create_eval_run()` as its first async operation. Frontend polls `job.progress.run_id` to redirect. If eval_run creation is delayed, frontend shows a blank job page.

2. **EvalRun always finalized.** Every code path (success, failure, cancel) must set eval_run to a terminal state. `recover_stale_eval_runs()` is a safety net, not a primary mechanism.

3. **Cancel never overwritten by fail/complete.** `finalize_eval_run()` has `WHERE status != 'cancelled'` guard for non-cancel finalizations. Any direct DB update must replicate this guard.

4. **JobCancelledError must propagate to worker_loop.** The worker_loop's success path does `db.refresh(job)` and checks `if job.status == "cancelled"` — this is a backup guard. But runners should still re-raise `JobCancelledError` so the except block's `j.status not in ("completed", "cancelled")` guard works correctly.

5. **`run_id` in job progress must be set early.** Frontend uses `progress.run_id` to redirect before the job completes. All runners write this immediately after `create_eval_run`.

6. **worker_loop error handler must reach terminal state.** The 3-retry loop at L238-258 ensures job failure is persisted even if DB is flaky. Don't add code paths that bypass this.

7. **Partial results are preserved on failure.** `PipelineStepError` (voice-rx) and per-thread error records (batch) save whatever succeeded before the failure. Don't discard partial results.

## Detailed Plans

- [Phase 1: Import Hygiene](./PHASE_1_IMPORT_HYGIENE.md)
- [Phase 2: Cancellation Chain](./PHASE_2_CANCELLATION_CHAIN.md)
- [Phase 3: Functional Gaps](./PHASE_3_FUNCTIONAL_GAPS.md)
- [Implementation Prompts](./IMPLEMENTATION_PROMPTS.md)
