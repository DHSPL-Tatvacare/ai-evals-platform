# Parallelization Engine for Kaira-Bot Evaluations

## Problem Statement

Batch and adversarial evaluation runners for kaira-bot process items sequentially
in `for` loops. With 50+ threads (batch) or 30+ test cases (adversarial), runs take
very long because each LLM call blocks the next. There was no way to run multiple
evaluations concurrently.

Additionally, the existing `parallel_custom_evals` toggle only parallelized custom
evaluators *within* a single thread — it didn't address the core bottleneck of
thread-level sequential processing.

## Solution

A unified parallelization engine (`run_parallel()`) that both runners use, controlled
by a simple UI toggle (on/off + worker count slider) on the Review step of each
overlay. With parallelism off (default), behavior is identical to before — no
separate code paths.

## Scope

Only kaira-bot batch (`batch_runner.py`) and adversarial (`adversarial_runner.py`).
Voice-rx pipeline was NOT touched.

## Files Changed

### New (2)

| File | Purpose |
|------|---------|
| `backend/app/services/evaluators/parallel_engine.py` | `run_parallel()` — semaphore-bounded concurrent execution with cancellation, progress, and inter-item delay |
| `src/features/evalRuns/components/ParallelConfigSection.tsx` | Reusable toggle + slider UI component |

### Modified (7)

| File | Change |
|------|--------|
| `backend/app/services/evaluators/llm_base.py` | Added `clone_for_thread()` to `LoggingLLMWrapper` |
| `backend/app/services/evaluators/batch_runner.py` | Extracted per-thread worker, replaced for-loop with `run_parallel()`, removed `parallel_custom_evals` |
| `backend/app/services/evaluators/adversarial_runner.py` | Extracted per-case worker, replaced for-loop with `run_parallel()` |
| `backend/app/services/job_worker.py` | Wired `parallel_threads`/`thread_workers` and `parallel_cases`/`case_workers` params |
| `src/features/evalRuns/components/NewBatchEvalOverlay.tsx` | Added parallel state + UI, removed `parallelCustomEvals` |
| `src/features/evalRuns/components/NewAdversarialOverlay.tsx` | Added parallel state + UI |
| `src/features/evalRuns/components/EvaluatorToggleStep.tsx` | Removed `parallelCustomEvals` checkbox and props |

## Key Design Decisions

- **Single function, not a class**: `run_parallel()` is ~70 lines, no state between calls.
- **Per-worker evaluator instances**: Each worker creates its own IntentEvaluator/CorrectnessEvaluator/etc. with a cloned LLM wrapper. Avoids shared mutable state (thread_id).
- **Shared inner LLM provider**: `clone_for_thread()` shares the underlying GeminiProvider/OpenAIProvider. Safe because `asyncio.to_thread()` creates per-call closures.
- **Sequential parity**: `concurrency=1` takes the exact same code path as a for loop.
- **Subsume parallel_custom_evals**: When thread parallelism is on, custom evals within each thread automatically run via `asyncio.gather`. No need for a separate toggle.

## Cleanup

`parallel_custom_evals` completely removed from: batch_runner, job_worker, NewBatchEvalOverlay, EvaluatorToggleStep. No references remain.

## Verification Checklist

1. Sequential parity: batch eval with parallelism OFF behaves identically to before
2. Parallel batch: 3 workers → progress bar advances, ThreadEvaluation rows persist correctly, ApiLog entries have correct thread_ids
3. Parallel adversarial: 3 workers → staggered starts (case_delay apart), AdversarialEvaluation rows persist
4. Cancellation: cancel mid-flight → remaining workers stop, EvalRun status = "cancelled"
5. Rate limits: existing `_with_retry` exponential backoff handles retries
6. UI: both overlays show toggle + slider on review step
