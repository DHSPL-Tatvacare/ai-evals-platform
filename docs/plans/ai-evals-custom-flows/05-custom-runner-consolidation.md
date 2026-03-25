# Custom Runner Consolidation & Unified Poll/Display Contract

## Current State: Two Files, Broken Contract

### What the two runner files do

**`custom_evaluator_runner.py` (370 lines)**
- Core logic: loads evaluator + entity, resolves prompt, calls LLM, saves EvalRun
- Handles both voice-rx (Listing) and kaira-bot (ChatSession) via `is_session_flow` flag
- Job type: `evaluate-custom`
- Creates: 1 EvalRun per execution
- **Has correct poll contract**: writes `run_id` to job.progress immediately

**`voice_rx_batch_custom_runner.py` (120 lines)**
- Pure orchestration: validates evaluator IDs, loops over them, calls `run_custom_evaluator()` for each
- Job type: `evaluate-custom-batch`
- Creates: N EvalRuns (one per evaluator)
- **Broken poll contract**: progress never includes `run_id`

### The real problem: Batch custom evals are second-class

| Aspect | Standard Pipeline | Custom Single | Custom Batch (Current) |
|--------|------------------|---------------|------------------------|
| **Job submission** | `useSubmitAndRedirect` | `evaluatorExecutor` → `submitAndPollJob` | `jobsApi.submit()` — fire and forget |
| **Job tracking** | `JobCompletionWatcher` | `JobCompletionWatcher` (via evaluatorExecutor) | **Not tracked** |
| **Progress UI** | RunDetail progress bar | Inline spinner | **Nothing** |
| **Redirect** | Polls run_id → RunDetail | Returns to overlay | **None** |
| **Cancel** | Cooperative from RunDetail | Abort controller | **No cancel UI** |

---

## The Fix: Three Steps

### Step 1: Merge runners into one file

Move `run_voice_rx_batch_custom()` into `custom_evaluator_runner.py` as `run_custom_eval_batch()`. Delete `voice_rx_batch_custom_runner.py`.

```python
# custom_evaluator_runner.py — add this function

async def run_custom_eval_batch(job_id, params: dict) -> dict:
    """Run multiple custom evaluators on a single entity. Creates N EvalRuns.

    Params:
        evaluator_ids: list[str]
        listing_id: str | None
        session_id: str | None
        app_id: str
        parallel: bool
        timeouts: dict
    """
    # Exact same logic as voice_rx_batch_custom_runner.py, but with run_id fix
    ...
```

Update `job_worker.py`:

```python
@register_job_handler("evaluate-custom-batch")
async def handle_evaluate_custom_batch(job_id, params: dict) -> dict:
    from app.services.evaluators.custom_evaluator_runner import run_custom_eval_batch
    return await run_custom_eval_batch(job_id=job_id, params=params)
```

### Step 2: Write `run_id` to batch progress

The batch creates N EvalRuns. We write the first completed run's ID to progress so the frontend can redirect somewhere useful.

**For parallel mode**: use `asyncio.as_completed()` instead of `asyncio.gather()` to get the first result:

```python
async def run_custom_eval_batch(job_id, params: dict) -> dict:
    ...
    first_run_id = None

    if parallel:
        tasks = {asyncio.create_task(_run_one(eid)): eid for eid in valid_ids}
        for coro in asyncio.as_completed(tasks):
            result = await coro
            if not first_run_id and result.get("eval_run_id"):
                first_run_id = result["eval_run_id"]
                await _update_progress(completed, total, f"Running...", run_id=first_run_id)
            completed += 1
    else:
        for i, eid in enumerate(valid_ids):
            result = await _run_one(eid)
            if not first_run_id and result.get("eval_run_id"):
                first_run_id = result["eval_run_id"]
            await _update_progress(i + 1, total, f"Running {i+1}/{total}...", run_id=first_run_id)

    ...
```

**Progress format** (consistent with all runners):
```python
{
    "current": N,
    "total": M,
    "message": "...",
    "run_id": "<first-completed-eval-run-uuid>"  # ← THIS IS THE FIX
}
```

### Step 3: Fix `RunAllOverlay.tsx` to use `useSubmitAndRedirect`

```tsx
// RunAllOverlay.tsx — REPLACE handleSubmit

import { useSubmitAndRedirect } from '@/hooks/useSubmitAndRedirect';

export function RunAllOverlay({ listingId, sessionId, appId, open, onClose }: RunAllOverlayProps) {
  // ...existing state...

  const { submit, isSubmitting } = useSubmitAndRedirect({
    appId,
    label: `${selected.size} Custom Evaluators`,
    successMessage: `Running ${selected.size} evaluator${selected.size !== 1 ? 's' : ''}...`,
    fallbackRoute: listingId
      ? `/voice-rx/listings/${listingId}`
      : `/kaira/sessions`,
    onClose,
  });

  async function handleSubmit() {
    if (selected.size === 0) return;
    await submit('evaluate-custom-batch', {
      evaluator_ids: Array.from(selected),
      listing_id: listingId,
      session_id: sessionId,
      app_id: appId,
      parallel: true,
    });
  }

  // ...rest unchanged, but use isSubmitting instead of local submitting state...
}
```

**Props change**: Add `sessionId?: string` to `RunAllOverlayProps`. The component now supports both voice-rx (listing) and kaira-bot (session).

Now batch custom follows the exact same pattern as batch thread and adversarial:
1. Submit job
2. Track in `JobCompletionWatcher`
3. Poll for `run_id` (up to 10s)
4. Redirect to `RunDetail` page (or entity page as fallback)
5. Completion toast

---

## Step 4: Extract shared runner boilerplate to `runner_utils.py`

Three categories of duplication exist across all 4 runners. All go into one new file.

**New file**: `backend/app/services/evaluators/runner_utils.py`

### 4a. `save_api_log()` — identical across 4 files

```python
"""Shared utilities for evaluation runners."""
import uuid
import logging
from datetime import datetime, timezone

from sqlalchemy import update

from app.database import async_session
from app.models.eval_run import EvalRun, ApiLog
from app.models.job import Job

logger = logging.getLogger(__name__)


async def save_api_log(log_entry: dict):
    """Persist an LLM API log entry to PostgreSQL."""
    run_id = log_entry.get("run_id")
    if run_id and isinstance(run_id, str):
        try:
            run_id = uuid.UUID(run_id)
        except ValueError:
            run_id = None

    async with async_session() as db:
        db.add(ApiLog(
            run_id=run_id,
            thread_id=log_entry.get("thread_id"),
            test_case_label=log_entry.get("test_case_label"),
            provider=log_entry.get("provider", "unknown"),
            model=log_entry.get("model", "unknown"),
            method=log_entry.get("method", "unknown"),
            prompt=log_entry.get("prompt", ""),
            system_prompt=log_entry.get("system_prompt"),
            response=log_entry.get("response"),
            error=log_entry.get("error"),
            duration_ms=log_entry.get("duration_ms"),
            tokens_in=log_entry.get("tokens_in"),
            tokens_out=log_entry.get("tokens_out"),
        ))
        await db.commit()
```

Then in each runner, replace local `_save_api_log` with:
```python
from app.services.evaluators.runner_utils import save_api_log
```

### 4b. `create_eval_run()` / `finalize_eval_run()` — EvalRun lifecycle boilerplate

Every runner has the same 3-phase pattern: create in "running" state, finalize to "completed", handle cancel/fail. Currently ~40 lines of boilerplate per runner × 4 = ~160 lines.

```python
async def create_eval_run(
    *,
    id: uuid.UUID,
    app_id: str,
    eval_type: str,
    job_id,
    listing_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    evaluator_id: uuid.UUID | None = None,
    batch_metadata: dict | None = None,
) -> None:
    """Create an EvalRun in 'running' state. Call at runner start."""
    async with async_session() as db:
        db.add(EvalRun(
            id=id,
            app_id=app_id,
            eval_type=eval_type,
            listing_id=listing_id,
            session_id=session_id,
            evaluator_id=evaluator_id,
            job_id=job_id,
            status="running",
            started_at=datetime.now(timezone.utc),
            batch_metadata=batch_metadata,
        ))
        await db.commit()


async def finalize_eval_run(
    run_id: uuid.UUID,
    *,
    status: str,
    duration_ms: float,
    result: dict | None = None,
    summary: dict | None = None,
    error_message: str | None = None,
) -> None:
    """Set terminal state on an EvalRun. Skips update if already cancelled.

    Handles all terminal states: completed, failed, cancelled.
    """
    values: dict = {
        "status": status,
        "completed_at": datetime.now(timezone.utc),
        "duration_ms": round(duration_ms, 2),
    }
    if result is not None:
        values["result"] = result
    if summary is not None:
        values["summary"] = summary
    if error_message is not None:
        values["error_message"] = error_message

    async with async_session() as db:
        # Don't overwrite a cancel that arrived during execution
        stmt = update(EvalRun).where(EvalRun.id == run_id)
        if status != "cancelled":
            stmt = stmt.where(EvalRun.status != "cancelled")
        await db.execute(stmt.values(**values))
        await db.commit()
```

Each runner goes from:
```python
# BEFORE (40 lines spread across try/except/except)
async with async_session() as db:
    db.add(EvalRun(id=..., status="running", ...))
    await db.commit()
# ...later...
async with async_session() as db:
    await db.execute(update(EvalRun).where(...).values(status="completed", ...))
    await db.commit()
# ...cancel handler...
async with async_session() as db:
    await db.execute(update(EvalRun).where(...).values(status="cancelled", ...))
    await db.commit()
# ...error handler...
async with async_session() as db:
    await db.execute(update(EvalRun).where(..., EvalRun.status != "cancelled").values(status="failed", ...))
    await db.commit()
```

To:
```python
# AFTER (4 lines)
await create_eval_run(id=eval_run_id, app_id=app_id, eval_type="custom", job_id=job_id, ...)
# ...later...
await finalize_eval_run(eval_run_id, status="completed", duration_ms=..., result=..., summary=...)
# ...cancel...
await finalize_eval_run(eval_run_id, status="cancelled", duration_ms=...)
# ...error...
await finalize_eval_run(eval_run_id, status="failed", duration_ms=..., error_message=...)
```

**Note**: Runners that store extra data (e.g. `config` snapshot, `llm_provider`, `llm_model`) still do their own `update(EvalRun)` for those — these helpers only handle the lifecycle state transitions. The `config` update happens between create and finalize and is runner-specific.

### 4c. Unify progress updates — expand `job_worker.update_job_progress()`

Currently 4 different patterns for writing job progress:

| Runner | Method |
|--------|--------|
| `voice_rx_runner` | Local `_update_progress(job_id, current, total, msg, listing_id, run_id)` |
| `batch_custom_runner` | Local `_update_progress(current, msg)` closure |
| `custom_evaluator_runner` | Inline `update(Job).where(...).values(progress={...})` |
| `adversarial_runner` / `batch_runner` | `progress_callback` → `job_worker.update_job_progress(job_id, current, total, msg)` |

`job_worker.py` already has `update_job_progress()` but it only accepts `(job_id, current, total, message)` and preserves existing `run_id`. It doesn't accept new `run_id` or other keys.

**Fix**: Expand the existing function to accept `**extra`:

```python
# job_worker.py — replace existing update_job_progress

async def update_job_progress(job_id, current: int, total: int, message: str = "", **extra):
    """Update job progress. Extra keys (run_id, listing_id, etc.) are merged in."""
    async with async_session() as db:
        job = await db.get(Job, job_id)
        if job:
            progress = {"current": current, "total": total, "message": message, **extra}
            # Preserve run_id from prior update if not overridden
            if isinstance(job.progress, dict) and "run_id" in job.progress and "run_id" not in extra:
                progress["run_id"] = job.progress["run_id"]
            job.progress = progress
            await db.commit()
```

Then all runners use `update_job_progress` directly:
```python
from app.services.job_worker import update_job_progress

# voice_rx_runner — delete local _update_progress, use:
await update_job_progress(job_id, 1, 3, "Transcribing...", run_id=str(eval_run_id), listing_id=listing_id)

# custom_evaluator_runner — delete inline SQL, use:
await update_job_progress(job_id, 0, 2, "Loading evaluator...", run_id=str(eval_run_id))

# batch_runner / adversarial_runner — already use it via progress_callback, no change needed
```

### 4d. `find_primary_field()` — shared score field detection

`batch_runner.py` has `_detect_primary_field()` and `custom_evaluator_runner.py` has the same logic inline in `_extract_scores()`. Both scan `output_schema` for `isMainMetric`, fall back to first number field. Extract to one function:

```python
def find_primary_field(output_schema: list[dict]) -> dict | None:
    """Find the primary metric field from an output schema.

    Priority: isMainMetric=True > first number field > first text field > first field.
    """
    if not output_schema:
        return None
    for f in output_schema:
        if f.get("isMainMetric"):
            return f
    for f in output_schema:
        if f.get("type") == "number":
            return f
    for f in output_schema:
        if f.get("type") == "text":
            return f
    return output_schema[0]
```

`batch_runner._detect_primary_field()` is deleted; it calls `find_primary_field()` instead.
`custom_evaluator_runner._extract_scores()` calls `find_primary_field()` instead of its own inline scan.

---

## Concrete File Changes

### Backend

| File | Change | Lines |
|------|--------|-------|
| `runner_utils.py` | **New** — `save_api_log`, `create_eval_run`, `finalize_eval_run`, `find_primary_field` | ~120 |
| `custom_evaluator_runner.py` | Add `run_custom_eval_batch()`; delete `_save_api_log`, inline EvalRun lifecycle, inline progress SQL; use `runner_utils` + `update_job_progress` | +60, -65 |
| `voice_rx_batch_custom_runner.py` | **DELETE** | -120 |
| `voice_rx_runner.py` | Delete `_save_api_log`, `_update_progress`, EvalRun lifecycle boilerplate; use `runner_utils` + `update_job_progress` | -70, +5 |
| `batch_runner.py` | Delete `_save_api_log`, `_detect_primary_field`, EvalRun lifecycle boilerplate; use `runner_utils` | -65, +5 |
| `adversarial_runner.py` | Delete `_save_api_log`, EvalRun lifecycle boilerplate; use `runner_utils` | -50, +5 |
| `job_worker.py` | Update `evaluate-custom-batch` import; expand `update_job_progress` with `**extra` | ~10 |

**Net**: +1 new file, -1 deleted file, ~-250 lines of duplication removed

### Frontend

| File | Change | Lines |
|------|--------|-------|
| `RunAllOverlay.tsx` | Replace `jobsApi.submit()` with `useSubmitAndRedirect`; add `sessionId` prop | ~20 |

---

## What NOT to Change

- **`run_custom_evaluator()` core logic** — Pipeline logic unchanged; only lifecycle calls replaced
- **`evaluatorExecutor.ts`** — Single custom eval flow already works correctly
- **`useEvaluatorRunner.ts`** — Already uses job tracker + polling correctly
- **`job_worker.py` worker_loop** — No changes to polling/dispatch
- **`eval_runs.py` routes** — Already handles all eval_types uniformly
- **`EvalRun` model** — No schema changes
- **Job types** — Keep `evaluate-custom` and `evaluate-custom-batch` (no renaming)
