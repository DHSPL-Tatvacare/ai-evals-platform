# Adversarial Runner Refactor

## Changes

### Parameters
- Added: `parallel_cases: bool = False`, `case_workers: int = 1`

### Refactored Loop → Worker

The per-case body (originally lines 188–242) was extracted into:

```python
async def _evaluate_one_case(_index: int, tc):
```

Each worker:
1. Creates `worker_llm = llm.clone_for_thread(f"adversarial-{_index}")` (when concurrency > 1)
2. Creates its own `AdversarialEvaluator(worker_llm)` — needed because it contains `ConversationAgent` with per-conversation state
3. Shares `KairaClient` (stateless — just auth_token + base_url)
4. Runs conversation, evaluates transcript, persists `AdversarialEvaluation` row
5. Updates shared `verdicts`, `categories`, `error_count`, `goal_achieved_count` dicts/counters

The `for` loop was replaced with:

```python
await run_parallel(
    items=cases,
    worker=_evaluate_one_case,
    concurrency=effective_concurrency,
    job_id=job_id,
    progress_callback=_progress_bridge,
    progress_message=_progress_message,
    inter_item_delay=case_delay,
)
```

### Rate Limiting

`inter_item_delay=case_delay` ensures staggered starts even with concurrent workers. The engine's `delay_lock` serializes the delay so workers don't all start at once.

### Cleanup
- Removed `check_cancelled()` helper (cancellation handled by `run_parallel`)
- Removed unused `asyncio` import, `is_job_cancelled` import
