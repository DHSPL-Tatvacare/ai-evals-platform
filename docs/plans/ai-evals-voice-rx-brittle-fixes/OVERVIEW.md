# Voice Rx Brittle Fixes — Master Plan

> Fix all 15 verified issues from the evaluation overlay execution pipeline audit.
> Organized into 4 phases by blast radius: data integrity first, then validation,
> then completeness, then frontend polish.

## Issue Registry

| ID  | Sev    | Layer    | Summary                                              | Phase |
|-----|--------|----------|------------------------------------------------------|-------|
| B9  | Medium | Backend  | Cancel race: runner overwrites `cancelled` → `completed` | 1 |
| B5  | Medium | Backend  | No critique response validation before storing       | 1 |
| B2  | Medium | Backend  | `skip_transcription` partially implemented (progress bug) | 1 |
| B1  | Medium | Backend  | Loose model family detection (`"3" in name`)         | 2 |
| B6  | Low    | Backend  | Timeout overrides accepted without validation        | 2 |
| B3  | Medium | Backend  | Normalization failure: no transient vs. user error distinction | 2 |
| B11 | Low    | Backend  | `repair_truncated_json` silently produces wrong JSON | 2 |
| B10 | Low    | Backend  | `_build_summary` returns None for incomplete evals   | 3 |
| B4  | Medium | Backend  | Dual script injection points can contradict          | 3 |
| X2  | Low    | Cross    | `run_id` fragile in `job.progress` JSON              | 3 |
| F2  | Low    | Frontend | No `cancelled` status badge in EvaluatorCard         | 4 |
| F3  | Medium | Frontend | `syncRuns` swallows errors silently                  | 4 |
| F4  | Low    | Frontend | Implicit ternary for listingId/sessionId fallback    | 4 |
| F5  | Low    | Frontend | Fork passes `''` instead of `null` for listing ID   | 4 |
| F1  | Low    | Frontend | RunAllOverlay shows only 100-char prompt truncation  | 4 |

## Phase Summary

| Phase | Name              | Issues | Risk | Files Touched |
|-------|-------------------|--------|------|---------------|
| 1     | Data Integrity    | B9, B5, B2 | High | voice_rx_runner.py, runner_utils.py, flow_config.py |
| 2     | Input Validation  | B1, B6, B3, B11 | Medium | llm_base.py, voice_rx_runner.py, response_parser.py |
| 3     | Completeness      | B10, B4, X2 | Low-Medium | voice_rx_runner.py, job_worker.py, models |
| 4     | Frontend Polish   | F2, F3, F4, F5, F1 | Low | EvaluatorCard.tsx, useEvaluatorRunner.ts, KairaBotEvaluatorsView.tsx, RunAllOverlay.tsx |

## Execution Rules

1. **One phase at a time.** Merge to `main` before starting next.
2. **Backend phases (1-3) before frontend (4).** Frontend depends on correct backend behavior.
3. **Each fix gets a manual test** described in the phase doc. No fix is "done" without its test passing.
4. **No scope creep.** Only fix what's listed. Don't refactor surrounding code.
5. **Preserve existing abstractions.** Use `finalize_eval_run`, `PipelineStepError`, etc.
6. **Run `npx tsc -b` + `npm run lint` after Phase 4.** Run backend startup after Phases 1-3.

## Branch Strategy

```
main
  └─ fix/brittle-phase-1-data-integrity
  └─ fix/brittle-phase-2-input-validation
  └─ fix/brittle-phase-3-completeness
  └─ fix/brittle-phase-4-frontend
```

Each branch from latest `main`. Merge before creating next.

## Invariants That Must Not Break

These are the critical contracts verified in the audit. Every phase must preserve them:

1. Two-call contract: transcription uses audio, critique is text-only
2. Standard pipeline prompts/schemas are hardcoded, not user-configurable
3. Comparison table is server-built, injected into prompt
4. Statistics are server-computed from known segment counts
5. Service account auth for managed jobs, API key for interactive
6. Cooperative cancellation checked at step boundaries
7. Config snapshot stored in eval_run.config for reproducibility
8. FlowConfig is frozen (immutable after creation)
9. Backend is source of truth for eval_runs (frontend merges, never overwrites)
10. `kaira-evals` appId must NOT be reintroduced in frontend

## File Index (all files touched across all phases)

### Backend
- `backend/app/services/evaluators/voice_rx_runner.py`
- `backend/app/services/evaluators/llm_base.py`
- `backend/app/services/evaluators/runner_utils.py`
- `backend/app/services/evaluators/response_parser.py`
- `backend/app/services/evaluators/flow_config.py`
- `backend/app/services/job_worker.py`

### Frontend
- `src/features/evals/components/EvaluatorCard.tsx`
- `src/features/evals/hooks/useEvaluatorRunner.ts`
- `src/features/voiceRx/components/RunAllOverlay.tsx`
- `src/features/kaira/components/KairaBotEvaluatorsView.tsx`

### Models (Phase 3 only, if X2 is implemented)
- `backend/app/models/job.py` (add `run_id` column)
- Alembic migration for new column
