# Phase 2: Cancellation Chain Repair

**Goal:** Fix 3 bugs (V1, M3, M1) that break cancel propagation in voice-rx and custom evaluator paths. After this phase, every cancel request must propagate cleanly through every code path for every job type.
**Risk Level:** Medium — logic changes in error handling paths. Requires careful testing.
**Files Changed:** `voice_rx_runner.py`, `custom_evaluator_runner.py`
**Files NOT Changed:** `batch_runner.py` (cancel chain is correct), `adversarial_runner.py` (cancel chain is correct), `job_worker.py`, `parallel_engine.py`, `runner_utils.py`
**Prerequisite:** Phase 1 must be completed first (import hygiene).

---

## How Cancellation Should Work (Reference)

The correct cancellation chain is implemented in `batch_runner.py` and `adversarial_runner.py`. Here's the reference:

```
1. User clicks cancel in frontend
2. Cancel API route: sets job.status="cancelled" in DB + calls mark_job_cancelled() (memory cache)
3. Runner periodically calls is_job_cancelled(job_id)
   - Memory-first check (instant)
   - DB fallback every 10 seconds
4. If cancelled: raise JobCancelledError("Job was cancelled by user")
5. Runner catches JobCancelledError:
   a. Finalizes eval_run as "cancelled" (via finalize_eval_run, which always applies for cancel status)
   b. RE-RAISES the exception (critical — this tells worker_loop the job ended via cancel)
6. Worker loop's try block: process_job raises JobCancelledError
   → Falls into except Exception (since JobCancelledError extends Exception)
   → Re-fetches job in fresh session
   → Checks j.status not in ("completed", "cancelled") — already cancelled, so skip
   → Job stays "cancelled"
7. _cleanup_cancelled_job removes from memory cache

Key invariants:
- finalize_eval_run with status="cancelled" has NO cancel-guard (it always applies)
- finalize_eval_run with status="failed" has cancel-guard (WHERE status != 'cancelled')
- Runner MUST re-raise after handling cancel (so worker_loop doesn't mark as "completed")
```

The backup guard in worker_loop (L214-217: `db.refresh(job)` + `if job.status == "cancelled"`) catches the case where the runner returns normally instead of raising. But relying on this backup is incorrect — it means the runner continued doing unnecessary work after cancel.

---

## Bug V1: `voice_rx_runner.py` — PipelineStepError Overwrites Cancel

### Problem

When a voice-rx evaluation fails at a pipeline step AND a cancel request arrives simultaneously:

```
Timeline:
  T0: Cancel route sets job.status="cancelled" in DB
  T1: Transcription/critique LLM call fails, raises Exception
  T2: Exception wrapped in PipelineStepError at L322 or L397
  T3: PipelineStepError caught at L444
  T4: Direct DB update at L454-467:
        UPDATE eval_runs SET status='failed' WHERE id=:run_id AND status != 'cancelled'
                                                                 ^^^^^^^^^^^^^^^^^^^^^^
                                                                 WAIT — this guard IS here
```

**Correction from initial analysis:** Reading the code more carefully at L456-458:

```python
await db.execute(
    update(EvalRun).where(
        EvalRun.id == eval_run_id,
        EvalRun.status != "cancelled",   # <-- guard IS present
    ).values(
        status="failed",
        ...
    )
)
```

The cancel guard IS present in the direct update. However, there is still a problem:

**The real V1 issue:** The `PipelineStepError` handler at L444-468 does a direct DB update and then **re-raises** (`raise` at L468). This re-raise sends `PipelineStepError` to the worker_loop's except block, which:

1. Detects `hasattr(e, 'step') and hasattr(e, 'message')` at L245 — yes
2. Sets `j.error_message = f"[{e.step}] {e.message}"[:2000]`
3. Sets `j.status = "failed"`
4. But checks `j.status not in ("completed", "cancelled")` at L242 first

So worker_loop also has the guard. The job stays cancelled if it was cancelled.

**Revised assessment:** V1 is actually correct for the status overwrite concern. The cancel guard works.

**However, the inconsistency remains a maintenance risk:** The `PipelineStepError` handler duplicates `finalize_eval_run`'s logic with raw SQL. If `finalize_eval_run` is ever updated (e.g., adding a new field to terminal-state records), the `PipelineStepError` handler won't pick up the change.

### Fix (Refactor, Not Behavioral)

Replace the direct DB update in the `PipelineStepError` handler (L454-467) with a call to `finalize_eval_run`, then re-raise. This makes the code consistent and eliminates the duplication.

**BEFORE** (L444-468):
```python
except PipelineStepError as e:
    evaluation["status"] = "failed"
    evaluation["error"] = e.message
    evaluation["failedStep"] = e.step
    if e.partial_result:
        for k, v in e.partial_result.items():
            if k not in evaluation:
                evaluation[k] = v

    async with async_session() as db:
        await db.execute(
            update(EvalRun).where(
                EvalRun.id == eval_run_id,
                EvalRun.status != "cancelled",
            ).values(
                status="failed",
                completed_at=datetime.now(timezone.utc),
                duration_ms=(time.monotonic() - start_time) * 1000,
                error_message=f"[{e.step}] {e.message}",
                result=evaluation,
            )
        )
        await db.commit()
    raise
```

**AFTER**:
```python
except PipelineStepError as e:
    evaluation["status"] = "failed"
    evaluation["error"] = e.message
    evaluation["failedStep"] = e.step
    if e.partial_result:
        for k, v in e.partial_result.items():
            if k not in evaluation:
                evaluation[k] = v

    await finalize_eval_run(
        eval_run_id,
        status="failed",
        duration_ms=(time.monotonic() - start_time) * 1000,
        error_message=f"[{e.step}] {e.message}",
        result=evaluation,
    )
    raise
```

### What NOT to Change

- Do NOT change the `except JobCancelledError` handler at L433-442. It is correct (uses `finalize_eval_run` and re-raises via the `raise` in the generic except that follows... actually wait, it doesn't re-raise. Let me check.)

**Additional finding:** The `except JobCancelledError` handler at L433-442:
```python
except JobCancelledError:
    evaluation["status"] = "cancelled"
    await finalize_eval_run(
        eval_run_id,
        status="cancelled",
        duration_ms=(time.monotonic() - start_time) * 1000,
        result=evaluation,
    )
    logger.info("Voice-RX evaluation for %s cancelled", listing_id)
    return {"listing_id": listing_id, "eval_run_id": str(eval_run_id), "status": "cancelled"}
```

This **returns** instead of **re-raising**. This is the same pattern as M3 in custom_evaluator_runner. The worker_loop's backup guard (`db.refresh` + cancel check at L214-217) will prevent the job from being marked "completed", so the job status is correct. But the runner is doing unnecessary work after the cancel detection point if there's any code after the return... there isn't in this case (it returns immediately). So this is acceptable for voice-rx because the return exits the function. The worker_loop backup guard handles the rest.

**However**, for consistency with batch_runner and adversarial_runner (which both re-raise), it would be better to re-raise. But this is a style choice, not a bug fix, because the return exits cleanly.

**Decision: Leave the voice-rx JobCancelledError handler as-is.** It returns immediately with correct data. The worker_loop backup guard ensures correct job status. Changing to re-raise would change the worker_loop's code path (from success-with-refresh to error-with-retry), which is a behavioral change we don't need.

---

## Bug M3: `custom_evaluator_runner.py` — `run_custom_evaluator` Swallows Cancel

### Problem

```python
# Lines 302-309 in run_custom_evaluator:
except JobCancelledError:
    await finalize_eval_run(
        eval_run_id,
        status="cancelled",
        duration_ms=(time.monotonic() - start_time) * 1000,
        error_message="Cancelled",
    )
    logger.info("Custom evaluator %s cancelled for %s", evaluator_id, entity_ref)

# Falls through to L323:
duration = time.monotonic() - start_time
result = {
    "evaluator_id": str(evaluator_id),
    "eval_run_id": str(eval_run_id),
    "status": "completed",       # <-- LIES. Was actually cancelled.
    ...
}
return result
```

When `run_custom_evaluator` is called directly by `handle_evaluate_custom` (single custom eval), this is tolerable — the worker_loop backup guard fixes the job status.

When `run_custom_evaluator` is called by `run_custom_eval_batch._run_one`, the returned `status: "completed"` makes the batch think the evaluator succeeded. It increments `completed` instead of propagating cancellation.

### Fix

After the `except JobCancelledError` block finalizes the eval_run, **re-raise** so the caller knows cancellation occurred:

**BEFORE** (L302-309):
```python
except JobCancelledError:
    await finalize_eval_run(
        eval_run_id,
        status="cancelled",
        duration_ms=(time.monotonic() - start_time) * 1000,
        error_message="Cancelled",
    )
    logger.info("Custom evaluator %s cancelled for %s", evaluator_id, entity_ref)
```

**AFTER**:
```python
except JobCancelledError:
    await finalize_eval_run(
        eval_run_id,
        status="cancelled",
        duration_ms=(time.monotonic() - start_time) * 1000,
        error_message="Cancelled",
    )
    logger.info("Custom evaluator %s cancelled for %s", evaluator_id, entity_ref)
    raise   # <-- propagate to caller
```

Then remove the fall-through code at L323-334 from executing after cancel. Since the exception is now re-raised, the code at L323 is only reached on success or after the `except Exception` block (which also re-raises). So the fall-through code is already unreachable after cancel. **No further changes needed to lines 323-334.**

### Downstream Impact

Adding `raise` changes the call chain:

**Single custom eval** (`handle_evaluate_custom` → `run_custom_evaluator`):
- Before: returns normally, worker_loop backup guard prevents "completed" overwrite.
- After: raises `JobCancelledError`, worker_loop's except block catches it, checks `j.status not in ("completed", "cancelled")` — job is already cancelled, skips. Same outcome, cleaner path.

**Batch custom eval** (`run_custom_eval_batch._run_one` → `run_custom_evaluator`):
- Before: returns `status: "completed"`, batch counts it as success.
- After: raises `JobCancelledError`, which `_run_one`'s `except Exception` catches... **wait, this needs M1 fix too.** See M1 below.

### What NOT to Change

- Do NOT change `finalize_eval_run` call params.
- Do NOT change the `except Exception` handler at L311-321 (it correctly re-raises).
- Do NOT change the return structure at L324-334 (only reached on success now).

---

## Bug M1: `custom_evaluator_runner.py` — `run_custom_eval_batch` Cancellation Dead Code

### Problem

The `_run_one` function in `run_custom_eval_batch` has this structure:

```python
async def _run_one(eid: str, index: int) -> dict:
    nonlocal completed, errors, first_run_id_written

    if await is_job_cancelled(job_id):              # <-- OUTSIDE try/except
        raise JobCancelledError("Batch cancelled")  # <-- escapes _run_one

    # ... inside try/except:
    try:
        result = await run_custom_evaluator(job_id=job_id, params=sub_params)
        # After M3 fix: run_custom_evaluator now raises JobCancelledError
        # This raise escapes the try block too!
        ...
    except Exception as e:
        errors += 1
        return {"evaluator_id": eid, "status": "failed", "error": ...}
```

When `parallel=True`:
```python
tasks = [_run_one(eid, i) for i, eid in enumerate(valid_ids)]
results = await asyncio.gather(*tasks, return_exceptions=True)
for i, r in enumerate(results):
    if isinstance(r, Exception):
        errors += 1            # <-- counts cancel as an error
```

`JobCancelledError` extends `Exception`, so `_run_one`'s except block catches it and returns a dict. After M3 fix, `run_custom_evaluator` will raise `JobCancelledError`, which `_run_one`'s `except Exception` catches, increments errors, and returns. The batch continues.

The outer `except JobCancelledError` at L433 is dead code in the parallel path because `gather(return_exceptions=True)` never raises.

### Fix

Restructure `_run_one` to let `JobCancelledError` propagate instead of catching it:

**BEFORE** (L379-416):
```python
async def _run_one(eid: str, index: int) -> dict:
    nonlocal completed, errors, first_run_id_written

    if await is_job_cancelled(job_id):
        raise JobCancelledError("Batch cancelled")

    sub_params = { ... }

    try:
        result = await run_custom_evaluator(job_id=job_id, params=sub_params)
        ...
        completed += 1
        return result
    except Exception as e:
        errors += 1
        logger.error("Batch custom eval %s failed: %s", eid, e)
        return {"evaluator_id": eid, "status": "failed", "error": safe_error_message(e)}
```

**AFTER**:
```python
async def _run_one(eid: str, index: int) -> dict:
    nonlocal completed, errors, first_run_id_written

    if await is_job_cancelled(job_id):
        raise JobCancelledError("Batch cancelled")

    sub_params = { ... }

    try:
        result = await run_custom_evaluator(job_id=job_id, params=sub_params)
        ...
        completed += 1
        return result
    except JobCancelledError:
        raise   # <-- propagate cancel, don't treat as error
    except Exception as e:
        errors += 1
        logger.error("Batch custom eval %s failed: %s", eid, e)
        return {"evaluator_id": eid, "status": "failed", "error": safe_error_message(e)}
```

Then change the parallel execution to NOT use `return_exceptions=True` and instead catch `JobCancelledError` at the gather level:

**BEFORE** (L418-435):
```python
try:
    if parallel:
        tasks = [_run_one(eid, i) for i, eid in enumerate(valid_ids)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                errors += 1
                logger.error("Batch custom eval %s raised: %s", valid_ids[i], r)
    else:
        for i, eid in enumerate(valid_ids):
            await update_job_progress(job_id, i, total, f"Running evaluator {i + 1}/{total}...")
            await _run_one(eid, i)

    await update_job_progress(job_id, total, total, f"Completed: {completed} success, {errors} failed")

except JobCancelledError:
    logger.info("Batch custom eval cancelled at %d/%d", completed, total)
    raise
```

**AFTER**:
```python
try:
    if parallel:
        tasks = [asyncio.create_task(_run_one(eid, i)) for i, eid in enumerate(valid_ids)]
        try:
            results = await asyncio.gather(*tasks)
        except JobCancelledError:
            # Cancel remaining tasks
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
    else:
        for i, eid in enumerate(valid_ids):
            await update_job_progress(job_id, i, total, f"Running evaluator {i + 1}/{total}...")
            await _run_one(eid, i)

    await update_job_progress(job_id, total, total, f"Completed: {completed} success, {errors} failed")

except JobCancelledError:
    logger.info("Batch custom eval cancelled at %d/%d", completed, total)
    raise
```

### Key Changes Explained

1. `_run_one`: Added `except JobCancelledError: raise` before `except Exception`. This lets cancel propagate while still catching regular errors.

2. Parallel path: Removed `return_exceptions=True`. Now `gather` will raise `JobCancelledError` when the first task encounters it. The inner try/except cancels remaining tasks (mirrors `parallel_engine.py`'s pattern at L105-113).

3. The outer `except JobCancelledError: raise` at L433 is now reachable in both parallel and sequential paths.

### What NOT to Change

- Do NOT change `_run_one`'s success path (result handling, `completed += 1`, first_run_id_written logic).
- Do NOT change the sequential path's `update_job_progress` call.
- Do NOT change the return value structure at L437-442.
- Do NOT change `run_custom_eval_batch`'s signature or params handling.

---

## Post-Fix Validation

### Critical: Cancellation Flow Tests

Test each of these scenarios. Each must result in:
- Job status: "cancelled"
- EvalRun status: "cancelled"
- No further LLM calls after cancel detection

| # | Scenario | Job Type | How to Test |
|---|---|---|---|
| C1 | Cancel voice-rx during transcription | evaluate-voice-rx | Start eval on a listing, cancel immediately (transcription is the longest step). Verify eval_run is "cancelled", not "failed". |
| C2 | Cancel voice-rx when transcription fails AND cancel arrives simultaneously | evaluate-voice-rx | Hard to reproduce exactly. Verify by reading code that `finalize_eval_run(status="failed")` in the PipelineStepError handler has cancel-guard (it does, via `finalize_eval_run`'s internal guard). |
| C3 | Cancel single custom eval during LLM call | evaluate-custom | Start custom eval, cancel during "Running evaluator..." phase. Verify eval_run is "cancelled". Verify `JobCancelledError` propagates to worker_loop (check logs for "Job X failed" — should NOT appear; should see worker_loop's "Job X was cancelled during execution" message). |
| C4 | Cancel custom eval batch (sequential) during 2nd evaluator | evaluate-custom-batch | Submit batch with 3+ evaluators, `parallel=false`. Cancel during 2nd. Verify: 1st eval_run completed, 2nd eval_run cancelled, 3rd eval_run never created. |
| C5 | Cancel custom eval batch (parallel) during execution | evaluate-custom-batch | Submit batch with 3+ evaluators, `parallel=true`. Cancel during execution. Verify: remaining tasks cancelled, no further LLM calls, job status "cancelled". |

### Regression: Non-Cancel Flows Must Still Work

| # | Flow | Job Type | What to Verify |
|---|---|---|---|
| R1 | Voice-rx eval completes successfully | evaluate-voice-rx | Transcription + optional normalization + critique all succeed. Eval_run status "completed". Summary computed. |
| R2 | Voice-rx eval fails at transcription | evaluate-voice-rx | PipelineStepError with step="transcription". Eval_run "failed" with partial result. Error message starts with "[transcription]". |
| R3 | Voice-rx eval fails at critique | evaluate-voice-rx | PipelineStepError with step="critique". Eval_run "failed" but has transcription results in result JSON. |
| R4 | Single custom eval completes | evaluate-custom | Output parsed, scores extracted, eval_run "completed" with summary. |
| R5 | Single custom eval fails (LLM error) | evaluate-custom | Eval_run "failed" with error message. Job "failed". |
| R6 | Custom eval batch completes (parallel) | evaluate-custom-batch | All eval_runs created and completed. Job "completed". |
| R7 | Custom eval batch partial failure (parallel) | evaluate-custom-batch | Some eval_runs "completed", some "failed". Job "completed". Counts correct. |
| R8 | Batch thread eval cancel | evaluate-batch | Already works. Verify still works. Eval_run "cancelled" with processed count. |
| R9 | Adversarial eval cancel | evaluate-adversarial | Already works. Verify still works. KairaClient session cleaned up. |

### Flow Chain Verification

After Phase 2, verify these chains are correct by reading the code (not just running):

1. **Cancel signal → runner detection**: `mark_job_cancelled()` → `_cancelled_jobs` set → `is_job_cancelled()` returns True. Unchanged.

2. **Runner detection → eval_run finalization**: `is_job_cancelled()` → raise `JobCancelledError` → except handler → `finalize_eval_run(status="cancelled")`. Verify all 5 job types.

3. **Runner detection → caller notification**: `JobCancelledError` re-raised in all runners. Verify:
   - `batch_runner.py` L575: catches, finalizes, re-raises via the raise. YES.
   - `adversarial_runner.py` L328: catches, finalizes, re-raises (implicit via `raise` or... let me check. L328-338: catches, calls `finalize_eval_run`, returns dict). Actually adversarial ALSO returns instead of re-raising. But this is acceptable because it returns directly to `handle_evaluate_adversarial` which returns to `process_job` which returns to worker_loop, and the backup guard catches it. **Leave as-is for adversarial too.**
   - `voice_rx_runner.py` L433: catches, finalizes, returns. Same pattern as adversarial. Acceptable.
   - `custom_evaluator_runner.py` L302: catches, finalizes, **now re-raises** (M3 fix). This is the change.
   - `custom_evaluator_runner.py` `_run_one`: **now lets JobCancelledError propagate** (M1 fix).

4. **worker_loop handling**: For runners that return (voice-rx, adversarial): backup guard at L214-217 (`db.refresh` + cancel check). For runners that raise (batch, custom after fix): except block at L231, guard at L242.
