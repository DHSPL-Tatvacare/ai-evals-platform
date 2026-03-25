# Batch Runner Refactor

## Changes

### Parameters
- Removed: `parallel_custom_evals: bool`
- Added: `parallel_threads: bool = False`, `thread_workers: int = 1`

### Refactored Loop → Worker

The per-thread body (originally lines 294–475) was extracted into:

```python
async def _evaluate_one_thread(_index: int, thread_id: str):
```

Each worker:
1. Creates `worker_llm = llm.clone_for_thread(thread_id)` (when concurrency > 1) for isolated API log attribution
2. Creates per-worker evaluator instances: `IntentEvaluator(worker_llm)`, `CorrectnessEvaluator(worker_llm)`, `EfficiencyEvaluator(worker_llm)`
3. Runs evaluators sequentially within the thread (intent → correctness → efficiency)
4. Runs custom evaluators via `asyncio.gather` when thread parallelism is on
5. Persists `ThreadEvaluation` row to DB
6. Updates `results_summary` dict (safe: single event loop, mutations between `await` points)

The `for` loop was replaced with:

```python
await run_parallel(
    items=ids_to_evaluate,
    worker=_evaluate_one_thread,
    concurrency=effective_concurrency,
    job_id=job_id,
    progress_callback=_progress_bridge,
    progress_message=_progress_message,
)
```

### Custom Eval Parallelism (Subsumed)

Old behavior: `parallel_custom_evals` flag controlled whether custom evaluators ran via `asyncio.gather` or sequentially within a thread.

New behavior: When `parallel_threads` is on, `run_custom_in_parallel = True` automatically. Custom evals within each thread run via `asyncio.gather`. When parallelism is off, custom evals run sequentially (same as before).

### Cleanup
- Removed top-level evaluator instances (`intent_eval`, `correctness_eval`, `efficiency_eval`) — now created per-worker
- Removed unused `select` import, `is_job_cancelled` import
