# Phase 4: Hardening — Listing Immutability, Validation, Error Boundaries

## Goal

Close all remaining edge cases:
1. Lock listing `sourceType` after initial data acquisition (prevent upload→API mixing)
2. Backend validates that job params match the listing's flow before executing
3. Each pipeline step has isolated error boundaries
4. Error propagation to UI is clear and actionable
5. UI disables cross-flow actions on committed listings

## Dependency

Phases 1-3 complete.

## Current State (Problems)

### Listing sourceType Mutability

1. `ListingUpdate` schema (line 26): `source_type: Optional[str] = None` — allows updating source_type
2. No backend validation prevents a listing from switching flows after data is committed
3. `ListingPage.tsx` line 314: When `sourceType === 'pending'`, both "Fetch from API" and "Upload Transcript" are shown — correct. But after choosing one, the listing can theoretically still be re-patched.

### Missing Backend Validation

4. `voice_rx_runner.py` does not validate that:
   - `listing.source_type` matches what the frontend claims
   - Required data exists (transcript for upload, api_response for API)
   - Schema is present when required (API flow needs transcription schema)
5. Some errors surface as generic Python exceptions — not user-friendly

### Error Boundaries

6. Pipeline errors mid-step can leave `evaluation` dict in partial state
7. No per-step error wrapping — a normalization failure takes down the entire eval
8. Frontend shows generic "Evaluation failed" without step-specific detail

## Changes

### 4.1 Backend: Listing sourceType Immutability

**File: `backend/app/routes/listings.py`**

Add validation in the update route: once a listing has acquired data (`sourceType` is not `pending`), reject attempts to change `sourceType`:

```python
@router.put("/api/listings/{listing_id}")
async def update_listing(listing_id: str, data: ListingUpdate, db: AsyncSession = Depends(get_db)):
    listing = await db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(404, "Listing not found")

    # ── sourceType immutability ──
    if data.source_type is not None and listing.source_type != "pending":
        if data.source_type != listing.source_type:
            raise HTTPException(
                400,
                f"Cannot change sourceType from '{listing.source_type}' to '{data.source_type}'. "
                f"Create a new listing for a different flow."
            )

    # ── Prevent cross-flow data mixing ──
    if listing.source_type == "upload" and data.api_response is not None:
        raise HTTPException(400, "Cannot add API response to an upload-flow listing.")
    if listing.source_type == "api" and data.transcript is not None:
        # Allow transcript from API flow (it comes from api_response parsing)
        # But prevent direct transcript upload on API listings
        pass  # Assess if this needs blocking

    # ... existing update logic ...
```

### 4.2 Backend: Pre-Execution Validation in Runner

**File: `backend/app/services/evaluators/voice_rx_runner.py`**

Add validation block after loading the listing, before creating the eval_run:

```python
async def run_voice_rx_evaluation(job_id, params: dict) -> dict:
    # ... load listing ...

    flow = FlowConfig.from_params(params, listing.source_type or "upload")

    # ── Pre-execution validation ──
    errors = _validate_pipeline_inputs(flow, listing, params)
    if errors:
        raise ValueError(f"Pipeline validation failed: {'; '.join(errors)}")

    # ... create eval_run, proceed with pipeline ...


def _validate_pipeline_inputs(flow: FlowConfig, listing, params: dict) -> list[str]:
    """Validate all inputs before starting the pipeline. Returns list of error messages."""
    errors = []

    # Audio file is always required
    if not listing.audio_file:
        errors.append("Listing has no audio file")

    if flow.flow_type == "upload":
        # Upload flow requires transcript with segments
        if not listing.transcript:
            errors.append("Upload flow requires a transcript")
        elif not listing.transcript.get("segments"):
            errors.append("Upload flow requires transcript with segments")

        # Skip transcription requires a previous completed eval
        if flow.skip_transcription:
            pass  # Validated later when loading previous transcript

    elif flow.flow_type == "api":
        # API flow requires api_response
        if not listing.api_response:
            errors.append("API flow requires an API response (fetch from API first)")

        # API flow requires transcription schema
        if not params.get("transcription_schema"):
            errors.append("API flow requires a transcription schema")

    # Normalization requires prerequisites
    if flow.normalize_original:
        prereqs = params.get("prerequisites", {})
        if not prereqs.get("targetScript") and not prereqs.get("target_script"):
            errors.append("Normalization requires targetScript in prerequisites")
        if not prereqs.get("sourceScript") and not prereqs.get("source_script"):
            errors.append("Normalization requires sourceScript in prerequisites")

    # Prompts required
    if not params.get("transcription_prompt"):
        errors.append("Transcription prompt is required")
    if not params.get("evaluation_prompt"):
        errors.append("Evaluation prompt is required")

    return errors
```

### 4.3 Backend: Per-Step Error Boundaries

Wrap each pipeline step in its own try/except that captures the step name and partial results:

```python
class PipelineStepError(Exception):
    """Error from a specific pipeline step with context."""
    def __init__(self, step: str, message: str, partial_result: dict | None = None):
        self.step = step
        self.message = message
        self.partial_result = partial_result
        super().__init__(f"Step '{step}' failed: {message}")


async def run_voice_rx_evaluation(job_id, params: dict) -> dict:
    # ... setup ...

    try:
        # ── STEP 1: Transcription ──
        if not flow.skip_transcription:
            try:
                # ... existing transcription code ...
            except JobCancelledError:
                raise  # Let cancellation propagate
            except Exception as e:
                raise PipelineStepError(
                    step="transcription",
                    message=safe_error_message(e),
                    partial_result=dict(evaluation),
                ) from e

        # ── STEP 2: Normalization ──
        if flow.normalize_original:
            try:
                # ... normalization code ...
            except JobCancelledError:
                raise
            except Exception as e:
                # Normalization failure is non-fatal — log warning and continue
                logger.warning("Normalization failed for %s: %s", listing_id, e)
                evaluation.setdefault("warnings", []).append(
                    f"Normalization failed: {safe_error_message(e)}. Continuing without normalization."
                )
                # DO NOT re-raise — normalization is optional

        # ── STEP 3: Critique ──
        try:
            # ... critique code ...
        except JobCancelledError:
            raise
        except Exception as e:
            raise PipelineStepError(
                step="critique",
                message=safe_error_message(e),
                partial_result=dict(evaluation),
            ) from e

    except JobCancelledError:
        # ... existing cancellation handling ...

    except PipelineStepError as e:
        # Save partial result with step-specific error
        evaluation["status"] = "failed"
        evaluation["error"] = e.message
        evaluation["failedStep"] = e.step
        if e.partial_result:
            evaluation.update(e.partial_result)

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

    except Exception as e:
        # ... existing generic error handling ...
```

**Key design decision**: Normalization failure is **non-fatal**. It logs a warning and continues without normalization. Transcription and critique failures are fatal.

### 4.4 Frontend: Show Step-Specific Errors

**File: `src/features/voiceRx/pages/VoiceRxRunDetail.tsx`**

In the `RunHeader` or error display, show step-specific failure information:

```typescript
// Read from result
const failedStep = (run.result as Record<string, unknown>)?.failedStep as string | undefined;
const errorMessage = run.errorMessage;

// Display
{run.status === 'failed' && (
  <div className="bg-[var(--surface-error)] border border-[var(--border-error)] rounded p-3 text-sm">
    <div className="flex items-center gap-2 text-[var(--color-error)]">
      <AlertTriangle className="h-4 w-4 shrink-0" />
      <strong>
        {failedStep
          ? `Failed during ${failedStep}`
          : 'Evaluation failed'}
      </strong>
    </div>
    {errorMessage && (
      <p className="mt-1 text-[var(--text-secondary)]">{errorMessage}</p>
    )}
  </div>
)}
```

### 4.5 Frontend: Show Normalization Warnings

When normalization failed but the eval continued:

```typescript
const warnings = (run.result as Record<string, unknown>)?.warnings as string[] | undefined;

{warnings && warnings.length > 0 && (
  <div className="bg-[var(--surface-warning)] border border-[var(--border-warning)] rounded p-2 text-xs text-[var(--color-warning)]">
    {warnings.map((w, i) => <p key={i}>{w}</p>)}
  </div>
)}
```

### 4.6 Frontend: Disable Cross-Flow Actions

**File: `src/app/pages/ListingPage.tsx`**

After `sourceType` is committed (not `pending`), disable the opposite flow's action buttons:

```typescript
// Current: only show split button when pending
{listing.sourceType === 'pending' && (
  <SplitButton ... />
)}

// After flow is committed:
{listing.sourceType === 'api' && (
  // Show "Refetch from API" button, but NOT "Upload Transcript"
  <Button onClick={handleRefetchFromApi}>Refetch from API</Button>
)}

{listing.sourceType === 'upload' && (
  // Show "Update Transcript" option, but NOT "Fetch from API"
  <Button onClick={handleUpdateTranscript}>Update Transcript</Button>
)}
```

The key principle: **Once a flow is chosen, the other flow's data-acquisition actions are hidden.** The user must create a new listing for the other flow.

### 4.7 Frontend: Listing Flow Badge

Show the listing's flow type prominently:

```typescript
// In ListingPage header, next to listing title
{listing.sourceType !== 'pending' && (
  <span className={cn(
    "px-2 py-0.5 rounded text-[10px] font-medium uppercase",
    listing.sourceType === 'upload'
      ? "bg-[var(--color-info)]/10 text-[var(--color-info)]"
      : "bg-[var(--color-accent-purple)]/10 text-[var(--color-accent-purple)]",
  )}>
    {listing.sourceType === 'upload' ? 'Upload Flow' : 'API Flow'}
  </span>
)}
```

This already exists partially in the EvaluationOverlay review step (line 2152-2162). Promote it to the listing header.

### 4.8 Backend: Job Worker Error Message Improvement

**File: `backend/app/services/job_worker.py`**

Ensure `PipelineStepError` is surfaced with step context:

```python
except PipelineStepError as e:
    error_msg = f"[{e.step}] {e.message}"
    # ... save to job.error_message with step prefix ...
```

### 4.9 EvalRun FlowType in List Endpoints

**File: `backend/app/routes/eval_runs.py`**

When listing eval_runs, include `flowType` so the frontend can display it:

```python
# In _run_to_dict or similar serialization
d["flowType"] = (r.result or {}).get("flowType") or (r.config or {}).get("source_type") or "upload"
```

This enables the VoiceRxRunList to show a flow badge per run.

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `backend/app/routes/listings.py` | **MODIFY** | sourceType immutability, cross-flow data blocking |
| `backend/app/services/evaluators/voice_rx_runner.py` | **MODIFY** | Pre-validation, per-step error boundaries, PipelineStepError |
| `backend/app/services/job_worker.py` | **MODIFY** | PipelineStepError handling |
| `src/app/pages/ListingPage.tsx` | **MODIFY** | Hide cross-flow actions, show flow badge |
| `src/features/voiceRx/pages/VoiceRxRunDetail.tsx` | **MODIFY** | Step-specific error display, warnings |
| `src/features/voiceRx/pages/VoiceRxRunList.tsx` | **MODIFY** | Flow badge per run (optional) |
| `backend/app/routes/eval_runs.py` | **MODIFY** | Surface flowType in list response |

## Verification Checklist

### Listing Immutability
- [ ] Create listing → status is `pending` → can choose Upload or API
- [ ] Choose Upload (add transcript) → `sourceType` becomes `upload`
- [ ] Try to PATCH `source_type: "api"` → backend returns 400
- [ ] Try to add `api_response` to upload listing → backend returns 400
- [ ] Choose API (fetch from API) → `sourceType` becomes `api`
- [ ] "Upload Transcript" button is NOT shown on API-committed listing
- [ ] "Fetch from API" button is NOT shown on upload-committed listing

### Pre-Execution Validation
- [ ] Submit upload eval with no transcript on listing → clear error: "Upload flow requires a transcript"
- [ ] Submit API eval with no api_response on listing → clear error: "API flow requires an API response"
- [ ] Submit API eval with no transcription schema → clear error: "API flow requires a transcription schema"
- [ ] Submit eval with normalization but no targetScript → clear error about prerequisites

### Error Boundaries
- [ ] Transcription step fails (e.g., LLM timeout) → eval_run saved with `failedStep: "transcription"`, status="failed"
- [ ] Normalization step fails → eval continues, warning added, final status="completed"
- [ ] Critique step fails → eval_run saved with `failedStep: "critique"`, partial transcription result preserved
- [ ] Job cancelled during normalization → status="cancelled", partial result preserved

### Error Display
- [ ] Failed eval shows step name: "Failed during transcription"
- [ ] Failed eval shows error message
- [ ] Eval with normalization warning shows yellow banner with warning text
- [ ] Partial results viewable even for failed evals (expand raw data)

### Flow Badge
- [ ] Listing page shows "Upload Flow" or "API Flow" badge
- [ ] VoiceRxRunList shows flow badge per run (if surfaced)
- [ ] VoiceRxRunDetail header shows flow type

### Cross-Flow Protection
- [ ] Cannot start API eval on upload-flow listing (validation catches missing api_response)
- [ ] Cannot start upload eval on API-flow listing (validation catches missing transcript with segments)
- [ ] Cannot mix data across flows on the same listing

### Regression
- [ ] All Phase 1-3 verification items still pass
- [ ] Old eval_runs display correctly
- [ ] New eval_runs display correctly in both flows
- [ ] Normalization toggle works in both flows
- [ ] Prompt/schema filtering still correct
