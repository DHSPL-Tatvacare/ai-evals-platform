# 01 — Types, Computation Logic & Hook Changes

## Files involved

| File | Action |
|---|---|
| `src/features/evals/metrics/types.ts` | Extend `ListingMetrics` with new fields |
| `src/features/evals/metrics/computeMetrics.ts` | Add API-flow-aware computation |
| `src/features/evals/hooks/useListingMetrics.ts` | Fix data source for API flow |
| `src/features/evals/metrics/index.ts` | Export new functions |

---

## 1. `types.ts` — Extend ListingMetrics

Current `ListingMetrics` only has `match`, `wer`, `cer`. Add API flow metrics.

```typescript
// Current
export interface ListingMetrics {
  match: MetricResult;
  wer: MetricResult;
  cer: MetricResult;
  computedAt: Date;
}

// Proposed
export interface ListingMetrics {
  // Common
  wer: MetricResult;
  cer: MetricResult;
  computedAt: Date;

  // Upload flow (segment match)
  match?: MetricResult;

  // API flow (field-level)
  fieldAccuracy?: MetricResult;
  extractionRecall?: MetricResult;
  extractionPrecision?: MetricResult;

  /** Which flow produced these metrics */
  flowType: 'upload' | 'api';
}
```

All consumers of `ListingMetrics` (MetricsBar, MetricCard) must handle optional fields. `flowType` lets the UI decide which cards to show.

---

## 2. `computeMetrics.ts` — API-flow-aware computation

### Current code

```typescript
export function computeAllMetrics(
  originalTranscript: TranscriptData,
  judgeTranscript: TranscriptData
): ListingMetrics {
  const originalText = transcriptToText(originalTranscript);  // BUG: empty for API flow
  const llmText = transcriptToText(judgeTranscript);
  const wer = calculateWERMetric(originalText, llmText);
  const cer = calculateCERMetric(originalText, llmText);
  const match = calculateMatchMetric(wer);
  return { match, wer, cer, computedAt: new Date() };
}
```

### Proposed: Add `computeApiFlowMetrics`

```typescript
import type { FieldCritique } from '@/types';

/**
 * Compute metrics for API flow evaluations.
 *
 * Inputs:
 *   apiTranscript:  apiResponse.input (the API's raw transcript string)
 *   judgeTranscript: judgeOutput.transcript (the judge's transcript string)
 *   fieldCritiques:  critique.fieldCritiques (array of per-field verdicts)
 */
export function computeApiFlowMetrics(
  apiTranscript: string,
  judgeTranscript: string,
  fieldCritiques: FieldCritique[],
): ListingMetrics {
  // ── Transcript metrics (WER/CER on full strings) ──
  const wer = calculateWERMetric(apiTranscript, judgeTranscript);
  const cer = calculateCERMetric(apiTranscript, judgeTranscript);

  // ── Field Accuracy ──
  // match: true count / total fieldCritiques
  const total = fieldCritiques.length;
  const matchCount = fieldCritiques.filter(fc => fc.match).length;
  const accuracyPct = total > 0 ? (matchCount / total) * 100 : 0;

  const fieldAccuracy: MetricResult = {
    id: 'fieldAccuracy',
    label: 'Field Accuracy',
    value: accuracyPct,
    displayValue: `${accuracyPct.toFixed(1)}%`,
    maxValue: 100,
    percentage: accuracyPct,
    rating: getRating(accuracyPct),
    description: `${matchCount}/${total} fields match — structured data correctness`,
  };

  // ── Extraction Recall ──
  // "Of all entries, how many has the API extracted (not '(not found)')?"
  // judge_only items have apiValue = "(not found)" — API missed them entirely
  const apiExtracted = fieldCritiques.filter(
    fc => String(fc.apiValue) !== '(not found)'
  ).length;
  const recallPct = total > 0 ? (apiExtracted / total) * 100 : 0;

  const extractionRecall: MetricResult = {
    id: 'extractionRecall',
    label: 'Recall',
    value: recallPct,
    displayValue: `${recallPct.toFixed(1)}%`,
    maxValue: 100,
    percentage: recallPct,
    rating: getRating(recallPct),
    description: `${apiExtracted}/${total} items captured — extraction completeness`,
  };

  // ── Extraction Precision ──
  // "Of everything the API extracted, how many were correct?"
  const apiCorrect = fieldCritiques.filter(
    fc => String(fc.apiValue) !== '(not found)' && fc.match
  ).length;
  const precisionPct = apiExtracted > 0 ? (apiCorrect / apiExtracted) * 100 : 0;

  const extractionPrecision: MetricResult = {
    id: 'extractionPrecision',
    label: 'Precision',
    value: precisionPct,
    displayValue: `${precisionPct.toFixed(1)}%`,
    maxValue: 100,
    percentage: precisionPct,
    rating: getRating(precisionPct),
    description: `${apiCorrect}/${apiExtracted} extracted values correct — extraction accuracy`,
  };

  return {
    wer,
    cer,
    fieldAccuracy,
    extractionRecall,
    extractionPrecision,
    flowType: 'api',
    computedAt: new Date(),
  };
}
```

### Keep existing `computeAllMetrics` for upload flow

Rename or adapt to return `flowType: 'upload'` and include `match`.

```typescript
export function computeUploadFlowMetrics(
  originalTranscript: TranscriptData,
  judgeTranscript: TranscriptData,
): ListingMetrics {
  const originalText = transcriptToText(originalTranscript);
  const llmText = transcriptToText(judgeTranscript);
  const wer = calculateWERMetric(originalText, llmText);
  const cer = calculateCERMetric(originalText, llmText);
  const match = calculateMatchMetric(wer);
  return { match, wer, cer, flowType: 'upload', computedAt: new Date() };
}
```

---

## 3. `useListingMetrics.ts` — Fix the hook

### Current code (broken for API flow)

```typescript
export function useListingMetrics(listing, aiEval): ListingMetrics | null {
  return useMemo(() => {
    if (!listing?.transcript || !aiEval?.judgeOutput) return null;
    if (aiEval.status !== 'completed') return null;

    const judgeTranscriptData = {
      fullTranscript: aiEval.judgeOutput.transcript,
      segments: aiEval.judgeOutput.segments ?? [],  // ← null for API flow → []
    } as unknown as TranscriptData;

    return computeAllMetrics(listing.transcript, judgeTranscriptData);
    // ↑ listing.transcript.segments is [] for API flow → empty text → WER=0
  }, [listing?.transcript, aiEval]);
}
```

### Proposed fix

```typescript
export function useListingMetrics(listing, aiEval): ListingMetrics | null {
  return useMemo(() => {
    if (!aiEval || aiEval.status !== 'completed' || !aiEval.judgeOutput) return null;

    const flowType = aiEval.flowType;

    if (flowType === 'api') {
      // API flow: use fullTranscript strings + fieldCritiques
      const apiTranscript = listing?.apiResponse?.input || '';
      const judgeTranscript = aiEval.judgeOutput.transcript || '';
      const fieldCritiques = aiEval.critique?.fieldCritiques ?? [];

      if (!apiTranscript && !judgeTranscript) return null;

      return computeApiFlowMetrics(apiTranscript, judgeTranscript, fieldCritiques);
    } else {
      // Upload flow: use segment-based transcripts
      if (!listing?.transcript) return null;

      const judgeTranscriptData = {
        fullTranscript: aiEval.judgeOutput.transcript,
        segments: aiEval.judgeOutput.segments ?? [],
      } as unknown as TranscriptData;

      return computeUploadFlowMetrics(listing.transcript, judgeTranscriptData);
    }
  }, [listing?.transcript, listing?.apiResponse, aiEval]);
}
```

Key changes:
- Branches on `aiEval.flowType` ('api' vs 'upload')
- API flow: uses `listing.apiResponse.input` and `aiEval.judgeOutput.transcript` as direct strings
- API flow: passes `fieldCritiques` for accuracy/recall/precision
- Upload flow: unchanged behavior

### Data availability check

| Field | Where it comes from | Always available? |
|---|---|---|
| `listing.apiResponse.input` | MyTatva API response, stored on listing | Yes for API flow |
| `aiEval.judgeOutput.transcript` | Judge LLM output, stored in eval_run result | Yes when eval completed |
| `aiEval.critique.fieldCritiques` | Critique LLM output, stored in eval_run result | Yes when eval completed |
| `aiEval.flowType` | Stored in eval_run result | Yes |

---

## 4. `index.ts` — Export additions

```typescript
export { computeApiFlowMetrics, computeUploadFlowMetrics } from './computeMetrics';
```

Remove or deprecate `computeAllMetrics` (rename to `computeUploadFlowMetrics`).

---

## WER/CER note for API flow

For API flow, WER/CER compares:
- **Reference**: `apiResponse.input` (the API system's transcript — system under test)
- **Hypothesis**: `judgeOutput.transcript` (the judge's transcript — ground truth)

This is inverted from the typical ASR convention where reference = ground truth. But for our use case, we're measuring "how different is the API transcript from the judge transcript" — the direction doesn't matter for WER/CER magnitude, only for interpreting substitutions/insertions/deletions.

If you want conventional orientation (reference = judge, hypothesis = API), swap the arguments:
```typescript
const wer = calculateWERMetric(judgeTranscript, apiTranscript);
```

Either way the WER value is the same. Just decide which framing makes more sense for the UI description text.

---

## Cross-script WER/CER caveat

If the API transcript is in Devanagari and the judge transcript is in Roman (or vice versa), WER/CER will be near 100% — every word/character is "different." This is expected and correct when normalization is OFF with different scripts. When normalization is ON, both should be in the same script, and WER/CER becomes meaningful.

The `normalizationMeta` on the eval run tells you whether normalization was applied. The UI could show a warning when normalization is OFF and scripts differ: "WER/CER may be inflated due to cross-script comparison."
