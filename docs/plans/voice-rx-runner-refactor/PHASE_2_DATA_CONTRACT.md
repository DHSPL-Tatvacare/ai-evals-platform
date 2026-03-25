# Phase 2: Frontend — Types + Display Components for Unified Shape

## Goal

Update frontend types and display components to read the unified result shape from Phase 1. No adapters, no fallbacks, no legacy handling. Old eval_runs are deleted before this phase. Components read `result.flowType` and `result.critique` directly.

## Pre-requisite

1. Phase 1 complete — backend produces unified shape.
2. **Old data wiped:**
   ```sql
   DELETE FROM api_logs;
   DELETE FROM eval_runs WHERE eval_type = 'full_evaluation';
   ```

## Current State (Problems)

> **Note**: Line numbers below are approximate — these files have active modifications.

### VoiceRxRunDetail.tsx (~lines 196-303)

1. **Line 199**: `const critique = (result?.critique ?? result?.apiCritique)` — two different keys
2. **Line 200**: `const segments = (critique?.segments ?? [])` — assumes segments always
3. **Lines 244-287**: Only renders segment comparison table — no field critique table for API flow

### EvalsView.tsx / SemanticAuditView.tsx / ApiEvalsView.tsx (ListingPage)

4. `EvalsView` checks `aiEval.critique` vs `aiEval.apiCritique` to decide which view
5. `SemanticAuditView` reads `aiEval.apiCritique.rawOutput.field_critiques`
6. `extractFieldCritiques.ts` has dual-shape detection logic

### Types

7. `AIEvaluation` type has both `critique` and `apiCritique` as separate optional fields
8. No `FlowType` type exists
9. `llmTranscript` is a separate key from `judgeOutput`

## Changes

### 2.1 Type Definitions

**File: `src/types/eval.types.ts`**

Replace the old split types with the unified contract:

```typescript
export type FlowType = 'upload' | 'api';

export interface JudgeOutput {
  transcript: string;
  segments?: Array<Record<string, unknown>>;    // Upload flow only
  structuredData?: Record<string, unknown>;      // API flow only
}

export interface NormalizedOriginal {
  fullTranscript: string;
  segments?: Array<Record<string, unknown>>;     // Upload flow only
}

export interface NormalizationMeta {
  enabled: boolean;
  sourceScript: string;
  targetScript: string;
  normalizedAt?: string;
}

export interface UnifiedCritique {
  flowType: FlowType;
  overallAssessment: string;
  statistics?: Record<string, unknown>;    // Upload flow only; absent for API flow

  // Upload flow
  segments?: Array<Record<string, unknown>>;
  assessmentReferences?: Array<Record<string, unknown>>;

  // API flow
  fieldCritiques?: FieldCritique[];
  transcriptComparison?: Record<string, unknown>;

  rawOutput: Record<string, unknown>;
  generatedAt?: string;
  model?: string;
}

export interface AIEvaluation {
  id: string;
  createdAt: string;
  status: string;
  flowType: FlowType;
  models: { transcription: string; evaluation: string };
  prompts: { transcription: string; evaluation: string };
  warnings?: string[];
  error?: string;
  failedStep?: string;

  judgeOutput: JudgeOutput;
  critique: UnifiedCritique;
  normalizedOriginal?: NormalizedOriginal;
  normalizationMeta?: NormalizationMeta;
}
```

**Delete**: `ApiEvaluationCritique`, `llmTranscript` type references, `apiCritique` field, `SemanticAuditResult` interface (dead — defined but never read by any component). These no longer exist.

### 2.2 Delete extractFieldCritiques.ts

**File: `src/features/evals/utils/extractFieldCritiques.ts`** — **DELETE**

This file existed to bridge two different critique shapes (`structuredComparison.fields` vs `rawOutput.field_critiques`). With the unified shape, `critique.fieldCritiques` IS the canonical array. No extraction/transformation needed.

Also delete `buildStructuredComparison()` — same reason.

Update all importers to read `critique.fieldCritiques` directly.

### 2.3 VoiceRxRunDetail.tsx — FullEvaluationDetail

Rewrite to read unified shape directly:

```typescript
function FullEvaluationDetail({ run }: { run: EvalRun }) {
  const result = run.result as AIEvaluation | undefined;
  const summary = run.summary as Record<string, unknown> | undefined;

  if (!result?.critique) {
    return <p className="text-sm text-[var(--text-muted)] italic">No evaluation data.</p>;
  }

  const flowType = result.flowType;

  return (
    <div className="space-y-4">
      {/* Summary stats — same unified keys for both flows */}
      {summary && <SummaryStats summary={summary} />}

      {/* Severity distribution — same for both flows */}
      {summary?.severity_distribution && (
        <DistributionBar
          distribution={summary.severity_distribution as Record<string, number>}
          order={['NONE', 'MINOR', 'MODERATE', 'CRITICAL']}
        />
      )}

      {/* Flow-specific detail — dispatched by explicit flowType */}
      {flowType === 'upload' && result.critique.segments ? (
        <SegmentTable segments={result.critique.segments} />
      ) : flowType === 'api' && result.critique.fieldCritiques ? (
        <FieldCritiqueTable
          fieldCritiques={result.critique.fieldCritiques}
          overallAssessment={result.critique.overallAssessment}
        />
      ) : (
        <p className="text-sm text-[var(--text-muted)] italic">No detail data.</p>
      )}

      {/* Raw data — always available */}
      <RawDataCollapsible result={result} />
    </div>
  );
}
```

**`FieldCritiqueTable`**: New sub-component. Renders `FieldCritique[]` in a table (fieldPath, apiValue, judgeValue, severity, critique). Reuse the column layout from `ApiStructuredComparison` — same grid, same severity badges.

### 2.4 EvalsView.tsx

Change flow dispatch from key-existence to `flowType`:

```typescript
// Current:
if (aiEval.critique) → <SegmentComparisonTable>
if (aiEval.apiCritique) → <ApiEvalsView>

// New:
const flowType = aiEval.flowType;
if (flowType === 'upload') → <SegmentComparisonTable critique={aiEval.critique} ... />
if (flowType === 'api') → <ApiEvalsView critique={aiEval.critique} ... />
```

### 2.5 ApiEvalsView.tsx

Update props to receive `UnifiedCritique` instead of the old `apiCritique`:

```typescript
interface ApiEvalsViewProps {
  listing: Listing;
  aiEval: AIEvaluation;  // reads aiEval.critique, aiEval.judgeOutput, etc.
}
```

Remove:
- `aiEval.apiCritique` references → use `aiEval.critique`
- `aiEval.apiCritique.rawOutput` → use `aiEval.critique.rawOutput`
- `extractFieldCritiques(aiEval.apiCritique)` → use `aiEval.critique.fieldCritiques` directly
- `buildStructuredComparison()` call → not needed

The `classicStructuredComparison` memo becomes trivial:
```typescript
const classicStructuredComparison = useMemo(() => {
  const fcs = aiEval.critique.fieldCritiques;
  if (!fcs || fcs.length === 0) return undefined;
  const matches = fcs.filter(c => c.match).length;
  return {
    fields: fcs,
    overallAccuracy: Math.round((matches / fcs.length) * 100),
    summary: aiEval.critique.overallAssessment || '',
  };
}, [aiEval.critique]);
```

### 2.6 SemanticAuditView.tsx

Update to read directly from unified critique:

```typescript
// Current:
const critiques = useMemo(
  () => extractFieldCritiques(aiEval?.apiCritique),
  [aiEval?.apiCritique],
);

// New:
const critiques = aiEval?.critique?.fieldCritiques ?? [];
```

Other changes:
- `aiEval?.judgeOutput?.transcript` — unchanged (same key in new shape)
- `aiEval?.judgeOutput?.structuredData` — unchanged
- `aiEval?.normalizedOriginal?.fullTranscript` — unchanged
- `aiEval?.normalizationMeta` — unchanged
- `aiEval?.critique?.overallAssessment` — was `aiEval?.apiCritique?.overallAssessment`

### 2.7 SegmentComparisonTable.tsx

Minimal changes. It already reads `critique.segments`, `critique.overallAssessment`, `critique.statistics`, `critique.assessmentReferences`. These keys exist in the unified shape under `result.critique`. Just update the prop type to receive `UnifiedCritique`.

### 2.8 Backend: eval_runs Route

**File: `backend/app/routes/eval_runs.py`**

Surface `flowType` at the top level of the response:

```python
def _run_to_dict(r: EvalRun) -> dict:
    # ... existing serialization ...
    result = r.result or {}
    config = r.config or {}
    d["flowType"] = result.get("flowType") or config.get("source_type") or "upload"
    return d
```

## Files to Modify/Delete

| File | Action | Description |
|------|--------|-------------|
| `src/types/eval.types.ts` | **REWRITE** | Unified types, delete old split types |
| `src/features/evals/utils/extractFieldCritiques.ts` | **DELETE** | No longer needed |
| `src/features/voiceRx/pages/VoiceRxRunDetail.tsx` | **REWRITE** `FullEvaluationDetail` | Read unified shape, dispatch by `flowType` |
| `src/features/evals/components/EvalsView.tsx` | **MODIFY** | Dispatch by `flowType` not key existence |
| `src/features/evals/components/ApiEvalsView.tsx` | **MODIFY** | Read from `critique` not `apiCritique` |
| `src/features/evals/components/SemanticAuditView.tsx` | **MODIFY** | Read `critique.fieldCritiques` directly |
| `src/features/evals/components/SegmentComparisonTable.tsx` | **MINOR** | Update prop type |
| `backend/app/routes/eval_runs.py` | **MODIFY** | Surface `flowType` |

## Verification Checklist

- [ ] `npx tsc -b` passes — no type errors from removed old types
- [ ] Trigger upload eval → VoiceRxRunDetail shows segment comparison table
- [ ] Trigger API eval → VoiceRxRunDetail shows field critique table (not "No segments")
- [ ] ListingPage > Full Evaluations > upload → SegmentComparisonTable renders
- [ ] ListingPage > Full Evaluations > API > Inspector → SemanticAuditView renders field critiques
- [ ] ListingPage > Full Evaluations > API > Classic → ApiStructuredComparison renders field table
- [ ] Upload flow with normalization → SourceTranscriptPane toggle appears
- [ ] API flow with normalization → SourceTranscriptPane toggle appears
- [ ] API flow normalization → SourceTranscriptPane renders plain text (no segments key in `normalizedOriginal`)
- [ ] Eval with `result: null` → graceful empty state, no crash
- [ ] SummaryStats handles missing `statistics` gracefully (API flow critique has no `statistics` key)
- [ ] SemanticAuditView NEVER receives segment data
- [ ] SegmentComparisonTable NEVER receives fieldCritique data
- [ ] No imports of `extractFieldCritiques` remain in codebase
- [ ] No references to `apiCritique` remain in codebase
- [ ] No references to `llmTranscript` remain in codebase (replaced by `judgeOutput`)
- [ ] No references to `semanticAuditResult` remain in codebase (dead type, deleted)
