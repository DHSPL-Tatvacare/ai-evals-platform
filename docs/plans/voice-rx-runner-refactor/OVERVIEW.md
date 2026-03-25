# Voice-RX Runner Refactor — Overview

## Problem Statement

The voice-rx evaluation pipeline has two flows (Upload and API) that share a single runner function with branching code paths. This has caused:

1. **Normalization not working for API flow** — gated by `and not is_api_flow` in the backend
2. **Frontend tables breaking** — components assume segment-based data exists for all eval types
3. **Prompt/schema bleeding** — upload prompts visible in API flow and vice versa in dropdowns
4. **No listing-level flow enforcement** — a listing can be mutated from upload to API or mixed
5. **Run detail page broken for API flow** — `VoiceRxRunDetail.FullEvaluationDetail` assumes `critique.segments` exists
6. **Summary data inconsistent** — upload and API flows compute different summary keys with no contract

## Design Principles

1. **`Listing.sourceType` is the single source of truth** — set once at data-acquisition time, immutable after
2. **One pipeline, parameterized by flow config** — no `if is_api_flow` scattered throughout; instead, a `FlowConfig` object controls behavior
3. **Prompts, schemas, and evaluators are tagged by `sourceType`** — UI only shows what applies to the active flow
4. **Error boundaries at every pipeline stage** — each step (transcription, normalization, critique) has isolated error handling
5. **Consistent result contract** — both flows produce the same top-level result keys; display components read from a unified shape
6. **Backend validates frontend contract** — the runner validates that inputs match the declared flow before executing
7. **Clean slate** — no backward compatibility with old result shapes. Old eval_runs are deleted before deployment. One shape, no adapters, no fallbacks.

## Architecture: FlowConfig-Driven Pipeline

```
Listing.sourceType  ──►  FlowConfig (frozen at eval start)  ──►  Pipeline Steps
       │                        │                                       │
       │                   Controls:                               Executes:
       │                   - requires_segments                     1. Transcription
       │                   - requires_rx_fields                    2. Normalization (optional)
       │                   - normalization_input_type              3. Critique
       │                   - critique_parser
       │                   - summary_builder
       │                   - available_variables
       └── Gates UI:
           - Prompt/schema dropdowns
           - Variable availability
           - Normalization checkbox default
           - API fetch / Upload transcript buttons
```

## Migration Step (Before Phase 1 Deploy)

**Delete all existing eval_runs and API logs:**
```sql
DELETE FROM api_logs;
DELETE FROM eval_runs WHERE eval_type = 'full_evaluation';
```
This clears old-shape data. Custom evaluator runs (`eval_type = 'custom'`) are unaffected — their shape is independent.

## Deployment Strategy

**Phases 1+2 MUST deploy atomically.** Between Phase 1 and Phase 2, the backend writes the new unified shape (`critique` with `flowType`, no `apiCritique`) but the frontend still reads the old shape. Any eval run created in that gap would be unreadable by the old frontend. Since we're doing a clean data wipe anyway, deploy both together to eliminate this window.

Phases 3 and 4 can deploy independently after.

## Phase Breakdown

| Phase | Focus | Files Changed | Risk |
|-------|-------|--------------|------|
| **Phase 1** | Backend: FlowConfig + unified pipeline runner | 3 backend files | Medium — changes core execution |
| **Phase 2** | Frontend: Types + display components for unified shape | 7 frontend files + 1 backend | Low — display-only, reads new shape directly |
| **Phase 3** | Frontend: Flow-gated UI (prompts, schemas, wizard) | ~8 frontend files | Low — filtering and gating |
| **Phase 4** | Hardening: Listing immutability, validation, error boundaries | 4 backend + 3 frontend files | Low — safety rails |

**Phase 1+2 ship together. Phase 3, 4 ship independently.**

## Key Contracts

### EvalRun.result (Unified Shape)

Both flows MUST produce this structure:

```typescript
{
  id: string;
  createdAt: string;
  status: "completed" | "failed" | "cancelled";
  models: { transcription: string; evaluation: string };
  prompts: { transcription: string; evaluation: string };
  warnings?: string[];
  error?: string;
  failedStep?: string;

  flowType: "upload" | "api";

  // Transcription output
  judgeOutput: {
    transcript: string;                          // Always a string (both flows)
    segments?: TranscriptSegment[];              // Upload flow only
    structuredData?: Record<string, unknown>;    // API flow only
  };

  // Normalization (optional, both flows)
  normalizedOriginal?: {
    fullTranscript: string;    // Always present when normalization ran
    segments?: Segment[];      // Upload flow only (segment-level normalization)
  };
  normalizationMeta?: {
    enabled: boolean;
    sourceScript: string;
    targetScript: string;
    normalizedAt: string;
  };

  // Critique output
  critique: {                                    // UNIFIED key (not apiCritique vs critique)
    flowType: "upload" | "api";                  // Redundant for safety
    overallAssessment: string;                   // Both flows
    statistics?: CritiqueStatistics;             // Upload flow (from LLM); absent for API flow

    // Flow-specific critique data
    segments?: SegmentCritique[];                // Upload flow: segment-level comparison
    fieldCritiques?: FieldCritique[];            // API flow: field-level comparison
    transcriptComparison?: TranscriptComparison; // API flow: transcript diff

    rawOutput: Record<string, unknown>;          // Both: full LLM response
    generatedAt: string;
    model: string;
  };
}
```

### EvalRun.summary (Unified Shape)

```typescript
{
  flow_type: "upload" | "api";
  overall_accuracy: number;                 // 0.0 - 1.0 (both flows)
  total_items: number;                      // segments for upload, fields for API
  severity_distribution: Record<string, number>;  // NONE/MINOR/MODERATE/CRITICAL
  critical_errors: number;
  moderate_errors: number;
  minor_errors: number;
  overall_score?: number;                   // If available from LLM
}
```

## File Impact Map

### Backend
| File | Phase | Changes |
|------|-------|---------|
| `voice_rx_runner.py` | 1 | Major: FlowConfig, unified pipeline, normalization for both flows |
| `response_parser.py` | 1 | No changes — output normalization in step functions |
| `prompt_resolver.py` | — | No changes — already reads `use_segments` from context |
| `seed_defaults.py` | 3 | Verify all prompts/schemas have correct `source_type` tags |
| `routes/prompts.py` | 3 | Add `source_type` query filter |
| `routes/schemas.py` | 3 | Add `source_type` query filter |
| `routes/listings.py` | 4 | Enforce sourceType immutability after data acquisition |
| `routes/eval_runs.py` | 2 | Surface `flowType` in response |

### Frontend
| File | Phase | Changes |
|------|-------|---------|
| `eval.types.ts` | 2 | Replace old types with unified types. Delete `apiCritique`, `llmTranscript` |
| `VoiceRxRunDetail.tsx` | 2 | Dispatch by `result.flowType`, not key existence |
| `EvalsView.tsx` | 2 | Read `critique.flowType` to choose component |
| `ApiEvalsView.tsx` | 2 | Read from `critique` (not `apiCritique`) |
| `SemanticAuditView.tsx` | 2 | Read from `critique.fieldCritiques` directly |
| `SegmentComparisonTable.tsx` | 2 | Read from `critique.segments` directly |
| `extractFieldCritiques.ts` | 2 | **DELETE** — no longer needed, `fieldCritiques` is the canonical shape |
| `EvaluationOverlay.tsx` | 3 | Filter prompt/schema dropdowns by `sourceType` |
| `promptsStore.ts` | 3 | Implement `sourceType` filtering in `getPromptsByType` |
| `schemasStore.ts` | 3 | Implement `sourceType` filtering |
| `ListingPage.tsx` | 4 | Disable cross-flow actions after sourceType is set |

## Verification Strategy

Each phase has specific verification steps:
- **Phase 1**: Backend — run both flows, check result structure matches contract
- **Phase 2**: Integration — verify frontend tables render correctly for both flows
- **Phase 3**: UI — verify dropdowns only show flow-appropriate items
- **Phase 4**: Edge cases — verify cross-flow actions are blocked

See individual phase docs for detailed verification checklists.
