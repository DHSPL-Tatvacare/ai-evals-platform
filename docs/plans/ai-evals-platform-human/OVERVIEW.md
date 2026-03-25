# Human Evaluations — Implementation Plan

## Context

The platform has AI evaluations working end-to-end for voice-rx (upload + API flows). Human evaluation exists as an incomplete UI-only notepad (`HumanEvalNotepad.tsx`, 724 lines) with no backend persistence — data is lost on refresh. The goal is to build a production-quality human review system that:

- Persists accept/reject/correct decisions per segment (upload) or per field (API)
- Reuses existing comparison tables by adding review columns (not creating new components)
- Provides a metrics toggle showing AI-computed vs human-adjusted values
- Uses a generic adapter pattern extensible to kaira-bot

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ EvalsView (orchestrator)                                │
│ ┌─────────────────────┐ ┌─────────────────────────────┐ │
│ │ AI Evaluation tab   │ │ Human Review tab             │ │
│ │                     │ │                              │ │
│ │ AIEvalStatus strip  │ │ HumanReviewStatus strip      │ │
│ │ MetricsBar          │ │ MetricsBar (toggle: AI/Human)│ │
│ │ ComparisonTable     │ │ SAME ComparisonTable         │ │
│ │ (read-only)         │ │ + review columns (editable)  │ │
│ │                     │ │ + Submit Review footer       │ │
│ └─────────────────────┘ └─────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
         │                           │
         │ fetchLatestRun            │ upsertHumanReview / fetchHumanReview
         │ eval_type=full_evaluation │ eval_type=human
         ▼                           ▼
┌─────────────────────────────────────────────────────────┐
│ Backend: eval_runs table                                │
│                                                         │
│ AI eval row:  eval_type='full_evaluation'               │
│               result = { critique, judgeOutput, ... }   │
│                                                         │
│ Human review: eval_type='human'                         │
│               config = { aiEvalRunId, reviewSchema }    │
│               result = { overallVerdict, items[] }      │
│               summary = { counts, adjustedMetrics }     │
└─────────────────────────────────────────────────────────┘
```

## Data Flow

1. User opens listing → AI eval fetched (`eval_type='full_evaluation'`)
2. Human review fetched (`GET /api/eval-runs/{aiRunId}/human-review`)
3. If exists, review data populates review columns in table
4. User edits verdicts → local dirty state tracked in hook
5. "Submit Review" → `PUT /api/eval-runs/{aiRunId}/human-review` → upserts eval_run row
6. Summary with adjustedMetrics returned → metrics toggle can switch views
7. On page reload, step 2 restores the saved review

## Generic Adapter: reviewSchema

| App | Source Type | reviewSchema | items[] shape |
|-----|-----------|--------------|---------------|
| voice-rx | upload | `segment_review` | `{ segmentIndex, verdict, correctedText?, comment? }` |
| voice-rx | api | `field_review` | `{ fieldPath, verdict, correctedValue?, comment? }` |
| kaira-bot | — | `thread_review` | `{ threadId, evaluatorType, originalVerdict, humanVerdict, comment? }` |

## File Manifest

**Modified (10 files)**:
- `backend/app/routes/eval_runs.py` — +2 endpoints
- `backend/app/schemas/eval_run.py` — +1 request schema
- `src/types/eval.types.ts` — Replace HumanEvaluation types
- `src/services/api/evalRunsApi.ts` — +3 methods
- `src/features/evals/components/SegmentComparisonTable.tsx` — +reviewMode, +Verdict column
- `src/features/evals/components/ApiStructuredComparison.tsx` — +reviewMode, +Verdict column
- `src/features/evals/components/SemanticAuditView.tsx` — +review action in JudgeVerdictPane
- `src/features/evals/components/MetricsBar.tsx` — +source toggle
- `src/features/evals/hooks/useListingMetrics.ts` — +humanReview param
- `src/features/evals/components/EvalsView.tsx` — Rewire Human Review tab

**Rewritten (1 file)**:
- `src/features/evals/hooks/useHumanEvaluation.ts` — Full rewrite

**Created (1 file)**:
- `src/features/evals/components/HumanReviewStatus.tsx` — Status strip

**Deleted (2 files)**:
- `src/features/evals/components/HumanEvalNotepad.tsx` (724 lines)
- `src/services/export/exporters/correctionsExporter.ts` (46 lines)

## Implementation Order

1. **Backend first** (01-BACKEND) — endpoints must exist before frontend can call them
2. **Types + API client** (02-TYPES-AND-API-CLIENT) — new types needed before components can use them
3. **Table extensions** (03-TABLE-EXTENSIONS) — add review columns to existing tables
4. **Hook rewrite** (05-ORCHESTRATION, hook part) — useHumanReview with API persistence
5. **EvalsView rewire** (05-ORCHESTRATION, view part) — connect everything
6. **Metrics toggle** (04-METRICS-TOGGLE) — add computation + toggle after core flow works
7. **Cleanup** (06-CLEANUP) — delete old files last, after everything is verified working

**Total estimated scope**: ~500 lines added, ~800 lines removed (net reduction).
