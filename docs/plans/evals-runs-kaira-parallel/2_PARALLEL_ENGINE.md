# Parallel Engine — `parallel_engine.py`

## Function Signature

```python
async def run_parallel(
    items: Sequence[T],
    worker: Callable[[int, T], Awaitable[R]],
    *,
    concurrency: int = 1,
    job_id,
    progress_callback,
    progress_message,
    inter_item_delay: float = 0,
) -> list[R | BaseException]:
```

## Internals

- `asyncio.Semaphore(concurrency)` bounds in-flight workers
- `asyncio.Lock()` serializes `inter_item_delay` (stagger case starts for adversarial)
- `completed_count` atomic increment (safe: single-threaded event loop)
- Results list preserves input order via `results[index]`
- Cancellation via `is_job_cancelled()` checked before semaphore acquire; on cancel, remaining tasks are cancelled via `task.cancel()`
- `concurrency=1` takes a sequential `for` loop path — no tasks created
- `concurrency>1` uses `asyncio.create_task()` + `asyncio.gather()`

## Progress Tracking

No changes to frontend progress UI needed. The engine calls `progress_callback(completed_count, total, message)` after each worker finishes. Frontend polls `job.progress` as before.

Progress message is customizable via `progress_message(ok, errors, current, total)`:
- Batch: `"Thread 7/20 (5 ok, 2 errors)"`
- Adversarial: `"Test case 3/15 (2 ok, 1 errors)"`
