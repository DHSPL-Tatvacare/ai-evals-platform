# Phase 1 — Data Integrity Guards

> Prevents wrong data from landing in the database. Highest priority.

## B9: Cancel race — runner overwrites `cancelled` back to `completed`

### Problem

When a user cancels a job, the cancel endpoint (`jobs.py:77-80`) sets both `Job.status`
and `EvalRun.status` to `"cancelled"` in a single transaction. Good.

But the runner's final write at `voice_rx_runner.py:424-434` is **unconditional**:

```python
await db.execute(
    update(EvalRun).where(EvalRun.id == eval_run_id).values(
        status="completed",
        ...
    )
)
```

There is a narrow window between the runner's last `check_cancel()` call (line 393)
and this final write where:
1. Runner passes last cancel check
2. Cancel route fires, sets eval_run to `"cancelled"`
3. Runner writes `"completed"`, overwriting the cancel

The `job_worker.py:239-244` code re-checks job status before writing `job.status = "completed"`,
but the eval_run was already written by the runner before the worker gets control back.

### Fix

Add a status guard to the runner's final write. Change `voice_rx_runner.py:424-434`:

**Before:**
```python
async with async_session() as db:
    await db.execute(
        update(EvalRun).where(EvalRun.id == eval_run_id).values(
            status="completed",
            completed_at=completed_at,
            duration_ms=duration_ms,
            result=evaluation,
            summary=summary_data,
        )
    )
    await db.commit()
```

**After:**
```python
async with async_session() as db:
    result = await db.execute(
        update(EvalRun)
        .where(
            EvalRun.id == eval_run_id,
            EvalRun.status != "cancelled",  # Don't overwrite cancel
        )
        .values(
            status="completed",
            completed_at=completed_at,
            duration_ms=duration_ms,
            result=evaluation,
            summary=summary_data,
        )
    )
    await db.commit()
    if result.rowcount == 0:
        logger.info(
            "Eval run %s was cancelled before completion write — skipping",
            eval_run_id,
        )
```

Also apply the same pattern to `finalize_eval_run` in `runner_utils.py:95-130`.
Currently `finalize_eval_run` already has a cancel guard (line 113-114):
```python
if status != "cancelled":
    condition = condition & (EvalRun.status != "cancelled")
```

This is correct for the `finalize_eval_run` path. But the runner's **success** path
at lines 424-434 bypasses `finalize_eval_run` entirely — it writes directly. So the
fix must be applied directly in the runner's success write.

### Files Changed
- `backend/app/services/evaluators/voice_rx_runner.py` — lines 424-434

### Test Plan

**Test B9-1: Cancel during critique step**
1. Start a voice-rx evaluation (upload flow)
2. Wait for progress to show "Generating critique..." (step 3)
3. Cancel the job via API: `POST /api/jobs/{job_id}/cancel`
4. Wait 5 seconds for runner to complete
5. Query eval_run: `GET /api/eval-runs?listing_id={id}&eval_type=full_evaluation`
6. **Assert:** eval_run.status === "cancelled" (NOT "completed")

**Test B9-2: Cancel after completion (no-op)**
1. Start a voice-rx evaluation, let it complete
2. Verify eval_run.status === "completed"
3. Attempt cancel: `POST /api/jobs/{job_id}/cancel` → expect 400
4. **Assert:** eval_run.status still "completed"

---

## B5: No critique response validation before storing

### Problem

At `voice_rx_runner.py:814-820`, the critique response from the LLM is stored
without validating required fields:

```python
if isinstance(critique_text, dict):
    parsed_critique = critique_text
else:
    parsed_critique = parse_critique_response(...)
```

If the LLM returns a dict missing `segments` or `overallAssessment`, downstream
code silently produces empty critique data. The eval_run gets `status: "completed"`
with a hollow result.

### Fix

Add validation after parsing, before building the critique structure.
Insert after line 820 in `voice_rx_runner.py`:

```python
# Validate required critique fields
if flow.requires_segments:
    if not parsed_critique.get("segments") and not isinstance(parsed_critique.get("segments"), list):
        raise PipelineStepError(
            step="critique",
            message="LLM critique response missing 'segments' array",
            partial_result=dict(evaluation),
        )
    if not parsed_critique.get("overallAssessment"):
        logger.warning("Critique response missing overallAssessment — using empty string")
else:
    # API flow: validate structuredComparison exists
    structured = parsed_critique.get("structuredComparison")
    if not structured or not isinstance(structured, dict):
        raise PipelineStepError(
            step="critique",
            message="LLM critique response missing 'structuredComparison' object",
            partial_result=dict(evaluation),
        )
```

**Design choice:** `overallAssessment` is a soft warning (not fatal) because
the segment data is the primary output. `segments` and `structuredComparison`
are hard requirements — without them the critique is meaningless.

### Files Changed
- `backend/app/services/evaluators/voice_rx_runner.py` — after line 820

### Test Plan

**Test B5-1: Valid critique passes through**
1. Run a normal evaluation end-to-end
2. **Assert:** eval_run.status === "completed", result.critique.segments is non-empty

**Test B5-2: Missing segments raises PipelineStepError**
1. Temporarily mock `generate_json` to return `{"overallAssessment": "test"}`
   (missing `segments` key)
2. Run evaluation
3. **Assert:** eval_run.status === "failed"
4. **Assert:** eval_run.error_message contains "[critique]" and "missing 'segments'"

**Test B5-3: Missing overallAssessment is non-fatal**
1. Mock `generate_json` to return `{"segments": [...]}`
   (has segments but no overallAssessment)
2. Run evaluation
3. **Assert:** eval_run.status === "completed" (not failed)
4. **Assert:** result.critique.overallAssessment === "" (empty string fallback)

---

## B2: `skip_transcription` partially implemented — progress bug

### Problem

`FlowConfig.skip_transcription` (`flow_config.py:20`) exists and is accepted via
`from_params` (line 61). It affects `total_steps` (lines 47-49) but the runner
at `voice_rx_runner.py:308-328` **always** runs transcription unconditionally.

If a caller passes `skip_transcription: true`:
- `total_steps` = 2 (normalization + critique, or just critique)
- But transcription still runs as step 1
- Progress would overflow: reports 3/2

This is a latent bug. Nobody sends `skip_transcription: true` today, but the
code path exists and would break progress tracking if triggered.

### Fix

**Remove the field entirely.** There is no use case for skipping transcription
in the voice-rx pipeline — the critique step depends on transcription output.

Changes:

1. **`flow_config.py`:** Remove `skip_transcription` field and simplify `total_steps`:

```python
@dataclass(frozen=True)
class FlowConfig:
    flow_type: FlowType
    normalize_original: bool = False

    # (remove skip_transcription entirely)

    @property
    def total_steps(self) -> int:
        steps = 2  # transcription + critique (always)
        if self.normalize_original:
            steps += 1
        return steps

    @classmethod
    def from_params(cls, params: dict, source_type: str) -> "FlowConfig":
        flow_type: FlowType = "api" if source_type == "api" else "upload"
        return cls(
            flow_type=flow_type,
            normalize_original=params.get("normalize_original", False),
        )
```

2. **Verify no callers pass `skip_transcription`:**
   - Search codebase for `skip_transcription` — should only appear in flow_config.py
   - Frontend `evaluatorExecutor.ts` doesn't send it
   - No job handler sends it

### Files Changed
- `backend/app/services/evaluators/flow_config.py` — remove field + simplify

### Test Plan

**Test B2-1: total_steps is correct**
1. Create FlowConfig with `normalize_original=False`: assert `total_steps == 2`
2. Create FlowConfig with `normalize_original=True`: assert `total_steps == 3`

**Test B2-2: from_params ignores skip_transcription**
1. Call `FlowConfig.from_params({"skip_transcription": True}, "upload")`
2. **Assert:** No error (unknown key silently ignored by `params.get`)
3. **Assert:** `total_steps == 2` (transcription + critique)

**Test B2-3: Backend startup check**
1. Start backend with `docker compose up --build`
2. Verify no import errors
3. Run a voice-rx evaluation end-to-end
4. Verify progress shows correct steps (2/2 or 3/3)

---

## Phase 1 Completion Checklist

- [ ] B9 fix applied and tested
- [ ] B5 validation added and tested
- [ ] B2 dead code removed and tested
- [ ] Backend starts cleanly: `docker compose up --build`
- [ ] Existing voice-rx evaluation (upload flow) completes successfully
- [ ] Existing voice-rx evaluation (API flow) completes successfully
- [ ] Cancel during evaluation sets status to "cancelled" (not overwritten)
- [ ] Merge to `main`
