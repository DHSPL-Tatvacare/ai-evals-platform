# Phase 4: Verification & Testing

## Pre-Deploy Checks

```bash
npx tsc -b                    # TypeScript type check
npm run lint                  # Frontend lint
docker compose up --build     # Backend starts cleanly
docker compose logs backend | grep -i "schema"  # Expect: "Updated schema_data for 'API: Transcript Schema'"
```

## Test Matrix

| ID | Flow | Test Case | Expected Outcome |
|----|------|-----------|-----------------|
| TC1 | API | Basic eval on listing with API response | `fieldCritiques[].fieldPath` like `rx.medications[0].dosage` |
| TC2 | API | Judge output completeness | `judgeOutput.structuredData` has all core rx fields |
| TC3 | API | apiValue/judgeValue types | All strings in fieldCritiques |
| TC4 | Upload | Regression — basic upload eval | Segment comparison works as before |
| TC5 | API | Normalization + API eval | Normalization runs, then critique uses deep comparison |
| TC6 | Either | Cancel mid-evaluation | Job + EvalRun both `cancelled` |
| TC7 | Either | LLM error propagation | `PipelineStepError` saved to `EvalRun.error_message` |
| TC8 | API | Frontend rendering | `FieldCritiqueTable` shows per-field rows with severity badges |
| TC9 | API | Summary accuracy | `overall_accuracy` reflects per-field match rate |

## Wiring Checklist

| System | What to Check |
|--------|---------------|
| Progress updates | Step messages show in UI during eval |
| Error propagation | Errors saved to both Job and EvalRun |
| LLM audit trail | API logs exist for critique call at `/api/eval-runs/{id}/logs` |
| Cancellation | Cancel works — both Job and EvalRun marked `cancelled` |
| Config snapshot | `EvalRun.config` has updated schema |
| Frontend rendering | No JS console errors in detail view |

## Rollback

| Phase | Steps |
|-------|-------|
| Phase 1 | Revert imports in runner, delete `evaluation_constants.py` |
| Phase 2 | Revert `_run_critique()`, delete `comparison_builder.py`, revert constants |
| Phase 3 | Remove `required` from rx schema in `seed_defaults.py`, restart |
