# Voice RX Evaluation Pipeline Cleanup

## Problem Statement

The Voice RX **API flow** evaluation produces unreliable, meaningless data. Three root causes:

| Bug | Severity | Location | Issue |
|-----|----------|----------|-------|
| **BUG 1** | CRITICAL | `seed_defaults.py` L288-392 | `rx` object has 12+ properties but ZERO marked `required` — Gemini legally returns `rx: {}` |
| **BUG 2** | CRITICAL | `voice_rx_runner.py` L1144-1162 | Critique comparison dumps whole arrays as JSON — LLM must figure out element alignment itself |
| **BUG 3** | MODERATE | `voice_rx_runner.py` L309-310 | `apiValue`/`judgeValue` have no `"type"` — Gemini returns mixed types, frontend can't render cleanly |

**Additionally**: All hardcoded constants (prompts, schemas, display names, normalization templates) live inline in `voice_rx_runner.py` (~330 lines of constants in a 1272-line file). User requests extraction for maintainability.

## Phases

| Phase | Focus | Files | Risk |
|-------|-------|-------|------|
| [Phase 1](./PHASE_1_EXTRACT_CONSTANTS.md) | Extract constants to `evaluation_constants.py` | 2 files (1 new, 1 modify) | LOW — pure refactor |
| [Phase 2](./PHASE_2_DEEP_COMPARISON.md) | Deep comparison builder + fix API eval schema/prompt | 3 files (1 new, 2 modify) | MEDIUM — new logic |
| [Phase 3](./PHASE_3_SEED_SCHEMA_FIX.md) | Add `required` to rx transcription schema | 1 file modify | LOW — schema-only |
| [Phase 4](./PHASE_4_VERIFICATION.md) | Test matrix + wiring verification | 0 files — manual testing | N/A |

## Dependency Order

```
Phase 1 ──> Phase 2 ──> Phase 3 ──> Phase 4
(refactor)  (new logic)  (schema)    (verify)
```

Phase 1 first because Phase 2 modifies the constants in the extracted module.
Phase 3 after Phase 2 so the deep comparison builder has richer data from a non-sparse judge output.

## Files Created/Modified

| File | Phase | Action |
|------|-------|--------|
| `backend/app/services/evaluators/evaluation_constants.py` | 1 | **CREATE** |
| `backend/app/services/evaluators/comparison_builder.py` | 2 | **CREATE** |
| `backend/app/services/evaluators/voice_rx_runner.py` | 1+2 | **MODIFY** |
| `backend/app/services/seed_defaults.py` | 3 | **MODIFY** |

## Wiring That Must Remain Intact

These existing systems must continue to work unchanged:

- **Progress updates**: `_update_progress(job_id, current, total, message)` — step messages displayed in frontend job polling
- **Error propagation**: `PipelineStepError(step, message, partial_result)` → caught by `job_worker.py` → saved to both `Job.error_message` and `EvalRun.error_message`
- **LLM audit trail**: `LoggingLLMWrapper._save_log()` → `_save_api_log()` → `ApiLog` table
- **Cooperative cancellation**: `is_job_cancelled()` / `JobCancelledError` checks between every pipeline step
- **Summary computation**: `_build_summary()` computes `overall_accuracy`, `total_items`, severity counts from `critique.fieldCritiques`
- **Config snapshot**: `EvalRun.config` stores schema/prompt/model snapshot at job start
- **Frontend rendering**: `FieldCritiqueTable` expects `FieldCritique[]` with `fieldPath`, `apiValue`, `judgeValue`, `match`, `severity`, `critique`
- **Backward compat**: `_extract_field_critiques_from_raw()` must still render old eval runs from before this fix

## Prompts to Execute Each Phase

```
Phase 1: "Implement Phase 1 from docs/plans/voice-rx-evals-cleanup/PHASE_1_EXTRACT_CONSTANTS.md — extract all hardcoded constants from voice_rx_runner.py into a new evaluation_constants.py module. Pure refactor, no behavior change."

Phase 2: "Implement Phase 2 from docs/plans/voice-rx-evals-cleanup/PHASE_2_DEEP_COMPARISON.md — create the deep comparison builder in comparison_builder.py, update API evaluation prompt/schema in evaluation_constants.py, and wire it into voice_rx_runner.py's _run_critique() API branch."

Phase 3: "Implement Phase 3 from docs/plans/voice-rx-evals-cleanup/PHASE_3_SEED_SCHEMA_FIX.md — add required fields to the rx object in the API transcription schema in seed_defaults.py."

Phase 4: "Follow the verification plan in docs/plans/voice-rx-evals-cleanup/PHASE_4_VERIFICATION.md — run type checks, docker build, and the manual test matrix."
```
