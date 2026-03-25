# Phase 3 — Completeness Fixes

> Improve data quality for edge cases and partial evaluations.

## B10: `_build_summary` returns None for incomplete evals

### Problem

`voice_rx_runner.py:915-918`:

```python
def _build_summary(flow: FlowConfig, evaluation: dict) -> dict | None:
    if evaluation.get("status") != "completed":
        return None
```

If an evaluation fails mid-pipeline (e.g., critique step fails but transcription
succeeded), `summary` is None. Frontend list views that show accuracy/error counts
have nothing to display. Users can't tell if the eval was 50% done or 0% done.

### Fix

Generate a partial summary for incomplete evaluations. Include a `completeness`
field to indicate the summary's reliability.

```python
def _build_summary(flow: FlowConfig, evaluation: dict) -> dict | None:
    """Build a consistent summary regardless of flow type.

    Returns partial summaries for incomplete evaluations so list views
    can show what was computed before failure.
    """
    status = evaluation.get("status", "unknown")
    critique = evaluation.get("critique", {})
    summary: dict = {"flow_type": flow.flow_type}

    # Determine completeness level
    has_transcription = bool(evaluation.get("judgeOutput"))
    has_critique = bool(critique)

    if status == "completed" and has_critique:
        summary["completeness"] = "full"
    elif has_critique:
        summary["completeness"] = "partial_with_critique"
    elif has_transcription:
        summary["completeness"] = "partial_transcription_only"
    else:
        # Nothing useful to summarize
        return None

    if status != "completed":
        summary["status"] = status
        summary["failed_step"] = evaluation.get("failedStep")

    # ... rest of existing summary logic (segments/API stats) unchanged ...
    # The existing code already handles missing critique gracefully via .get()
```

The key change is:
1. Remove the early `return None` for non-completed status
2. Add `completeness` field
3. Let the existing `.get()` chains handle missing data naturally
4. Only return None if there's truly nothing (no transcription, no critique)

### Files Changed
- `backend/app/services/evaluators/voice_rx_runner.py` — `_build_summary()` (lines 915-978)

### Test Plan

**Test B10-1: Completed eval produces full summary**
1. Run successful evaluation
2. **Assert:** summary.completeness === "full"
3. **Assert:** summary has all expected fields (overall_accuracy, total_items, etc.)

**Test B10-2: Failed-at-critique produces partial summary**
1. Mock critique step to fail (raise PipelineStepError)
2. Run evaluation (transcription succeeds, critique fails)
3. **Assert:** eval_run.summary is NOT None
4. **Assert:** summary.completeness === "partial_transcription_only"
5. **Assert:** summary.failed_step === "critique"

**Test B10-3: Failed-at-transcription produces None**
1. Mock transcription to fail immediately
2. **Assert:** eval_run.summary is None (nothing to summarize)

---

## B4: Dual script injection points can contradict

### Problem

Script constraints are injected in TWO places during transcription:

1. **`resolve_prompt()`** at line 515 substitutes `{{script_instruction}}` variable
   inside the prompt template. This comes from `_resolve_single("script_instruction")`
   in `prompt_resolver.py:219-237`.

2. **Hard directive** at lines 550-557 PREPENDS to the prompt:
   ```python
   script_directive = (
       f">>> MANDATORY OUTPUT SCRIPT: {script_display} <<<\n"
       ...
   )
   final_prompt = script_directive + final_prompt
   ```

These use the same `script_display` value, so they currently agree. But:
- If `resolve_prompt` fails to resolve `{{script_instruction}}`, the raw token
  stays in the prompt alongside the directive
- If someone changes the prompt template to use a different variable name,
  the directive and template could diverge
- Two injection points make maintenance harder

### Fix

Consolidate to a single injection strategy. Keep the directive approach (it's
proven more effective for model compliance) and make `{{script_instruction}}`
always resolve to empty when the directive is present.

In `voice_rx_runner.py`, after `resolve_prompt()` at line 515:

```python
resolved = resolve_prompt(prompt_text, resolve_ctx)
final_prompt = resolved["prompt"]

# Replace audio placeholder
final_prompt = final_prompt.replace("{{audio}}", "[Audio file attached]")

# Script enforcement: single injection point (directive at top of prompt).
# Clear any {{script_instruction}} that resolve_prompt may have left in the
# prompt — the directive is the authoritative script constraint.
output_script = prerequisites.get("outputScript", "")
script_display = resolve_script_name(output_script) if output_script != "auto" else ""

if script_display:
    # Remove resolved script_instruction content to avoid duplication
    # (resolve_prompt may have already inserted it)
    # The directive below is the sole script enforcement.
    script_directive = (
        f">>> MANDATORY OUTPUT SCRIPT: {script_display} <<<\n"
        f"ALL text you produce MUST be in {script_display} script. "
        "Do NOT use Devanagari, Arabic, or any other script. "
        "This applies to every field in your output.\n\n"
    )
    final_prompt = script_directive + final_prompt
```

And in `prompt_resolver.py`, update `_resolve_single` for `script_instruction`
to add a comment noting it may be overridden:

```python
# Note: For voice-rx transcription, the runner prepends a hard
# directive that takes precedence over this resolved value.
# This variable still resolves for use in custom evaluator prompts.
```

**No functional change to prompt_resolver.** The resolver keeps working for
custom evaluators that use `{{script_instruction}}`. The runner just ensures
the directive is the authoritative constraint for the standard pipeline.

### Files Changed
- `backend/app/services/evaluators/voice_rx_runner.py` — lines 506-557 (restructure)
- `backend/app/services/evaluators/prompt_resolver.py` — add comment only

### Test Plan

**Test B4-1: Script directive present for non-auto script**
1. Run evaluation with `outputScript: "roman"`
2. Check eval_run.config.prompts.transcription
3. **Assert:** prompt starts with ">>> MANDATORY OUTPUT SCRIPT:"

**Test B4-2: No directive for auto script**
1. Run evaluation with `outputScript: "auto"`
2. **Assert:** prompt does NOT start with ">>> MANDATORY"

**Test B4-3: Custom evaluator still gets {{script_instruction}}**
1. Create custom evaluator with prompt containing `{{script_instruction}}`
2. Run custom evaluator with `targetScript: "devanagari"` in prerequisites
3. **Assert:** resolved prompt contains Devanagari instruction (not raw `{{script_instruction}}`)

---

## X2: `run_id` fragile in `job.progress` JSON

### Problem

`job_worker.py:155-161` preserves `run_id` inside the `job.progress` JSON dict:

```python
if (
    "run_id" not in extra
    and isinstance(job.progress, dict)
    and "run_id" in job.progress
):
    new_progress["run_id"] = job.progress["run_id"]
```

This is fragile because:
- `run_id` is semantically a first-class relationship (eval_run → job)
- It's buried in a dict that's overwritten on every progress update
- If `progress` is corrupted or None, `run_id` is lost
- The completion path at `job_worker.py:249-260` has its own preservation logic

### Fix

**Option A (recommended): Add `run_id` as a column on Job model.**

This requires a DB migration. Since this project uses direct `metadata.create_all`
(no Alembic), the change is:

1. Add column to `backend/app/models/job.py`:
   ```python
   run_id = Column(String, nullable=True)  # UUID of primary eval_run
   ```

2. Update `create_eval_run` in `runner_utils.py` to also set `Job.run_id`:
   ```python
   # After creating eval_run, link back to job
   if job_id:
       await db.execute(
           update(Job).where(Job.id == job_id).values(run_id=str(id))
       )
   ```

3. Update `update_job_progress` to stop managing `run_id` in progress dict:
   - Remove the preservation logic (lines 155-161)
   - The `run_id` kwarg can still be passed for backward compat but stored on column

4. Update `job_worker.py` completion path to stop preserving from progress dict.

5. Update `JobResponse` schema to expose `run_id` field.

**Option B (minimal): Keep in progress but add safety.**

If the migration is too risky, add a safety check:

```python
async def update_job_progress(job_id, current, total, message="", **extra):
    async with async_session() as db:
        job = await db.get(Job, job_id)
        if not job:
            return

        new_progress = {"current": current, "total": total, "message": message, **extra}

        # Preserve run_id from previous progress (first-class metadata)
        existing_run_id = (
            job.progress.get("run_id")
            if isinstance(job.progress, dict)
            else None
        )
        if existing_run_id and "run_id" not in extra:
            new_progress["run_id"] = existing_run_id

        job.progress = new_progress
        await db.commit()
```

This is what exists today but extracted into clearer variable names.

### Decision: Go with Option B (minimal safety) for this fix round.
Option A is the right long-term architecture but involves a model change + migration
that should be its own focused effort, not buried in a brittle-fix batch.

### Files Changed
- `backend/app/services/job_worker.py` — `update_job_progress()` (lines 137-163)

### Test Plan

**Test X2-1: run_id preserved across progress updates**
1. Create job, create eval_run linked to it
2. Call `update_job_progress(job_id, 1, 3, "Step 1", run_id="abc-123")`
3. Call `update_job_progress(job_id, 2, 3, "Step 2")` — no run_id
4. Fetch job: **Assert:** `job.progress["run_id"] == "abc-123"` (preserved)

**Test X2-2: run_id not overwritten by different value**
1. Set progress with `run_id="first"`
2. Update progress with `run_id="second"`
3. **Assert:** `job.progress["run_id"] == "second"` (explicit override wins)

**Test X2-3: Corrupted progress doesn't crash**
1. Manually set `job.progress = "garbage string"` in DB
2. Call `update_job_progress(job_id, 1, 3, "test")`
3. **Assert:** no crash, progress is replaced with valid dict

---

## Phase 3 Completion Checklist

- [ ] B10 partial summary implemented and tested
- [ ] B4 script injection consolidated and tested
- [ ] X2 run_id preservation hardened and tested
- [ ] Backend starts cleanly: `docker compose up --build`
- [ ] Existing evaluations (both flows) complete with correct summaries
- [ ] Failed evaluations now have partial summaries in list views
- [ ] Merge to `main`
