# Phase 04 — Metrics Toggle

## Human-Adjusted Metrics Computation

### New functions in `src/features/evals/metrics/computeMetrics.ts`

```typescript
/**
 * Upload flow: recompute metrics treating human verdicts as ground truth.
 * - Accepted segments: treated as matches (WER contribution = 0 for that segment)
 * - Corrected segments: WER/CER computed between correctedText and originalText
 * - Rejected segments: treated as full mismatches
 * - Unreviewed: use original AI metrics for those segments
 */
export function computeHumanAdjustedUploadMetrics(
  originalTranscript: TranscriptData,
  judgeTranscript: TranscriptData,
  segmentReviews: Map<number, SegmentReviewItem>,
): MetricResult[]

/**
 * API flow: recompute field accuracy based on human verdicts.
 * - Accepted fields: count as matches
 * - Corrected fields: count as matches (human provided correct value)
 * - Rejected fields: count as mismatches
 */
export function computeHumanAdjustedApiMetrics(
  apiTranscript: string,
  judgeTranscript: string,
  fieldCritiques: FieldCritique[],
  fieldReviews: Map<string, FieldReviewItem>,
): MetricResult[]
```

### Upload flow logic

- Build adjusted text by walking segments: if reviewed as 'accept', use judgeText. If 'correct', use correctedText. If 'reject', use originalText (mismatch). If unreviewed, use judgeText as-is.
- Recompute WER/CER between originalText and this adjusted text.
- Match% = 100 - WER.

### API flow logic

- Walk fieldCritiques. For each field, check if reviewed:
  - 'accept' → count as match
  - 'correct' → count as match (human corrected it)
  - 'reject' → count as mismatch
  - unreviewed → use original `field.match`
- Recompute fieldAccuracy, recall, precision from adjusted counts.
- WER/CER stay the same (transcript-level, not field-level).

---

## useListingMetrics Hook Extension

### Current signature

`useListingMetrics(listing, aiEval) → MetricResult[] | null`

### New signature

```typescript
export function useListingMetrics(
  listing: Listing | null,
  aiEval?: AIEvaluation | null,
  humanReview?: HumanReview | null,
  metricsSource?: 'ai' | 'human',
): MetricResult[] | null
```

### Logic

- If `metricsSource === 'ai'` or no humanReview: return existing AI metrics (unchanged)
- If `metricsSource === 'human'` and humanReview exists:
  - Parse `humanReview.result.items` into Map
  - Call `computeHumanAdjustedUploadMetrics` or `computeHumanAdjustedApiMetrics`
  - Return adjusted MetricResult[]
- Shortcut: if `humanReview.summary.adjustedMetrics` exists (pre-computed on submit), can build MetricResult[] directly from summary without recomputing. This avoids redundant computation on load.

---

## MetricsBar Toggle

### Change to `src/features/evals/components/MetricsBar.tsx`

#### New props

```typescript
interface MetricsBarProps {
  metrics: MetricResult[] | null;
  /** If provided, shows source toggle */
  hasHumanReview?: boolean;
  /** Current source: 'ai' or 'human' */
  metricsSource?: 'ai' | 'human';
  /** Callback when source toggles */
  onMetricsSourceChange?: (source: 'ai' | 'human') => void;
}
```

#### UI

When `hasHumanReview=true`, render a small toggle bar above the metrics grid:
```
[ AI Computed | Human Reviewed ]
```

- Two pill buttons (same style as severity filter chips)
- Active state: brand-primary bg
- Clicking toggles `metricsSource` via callback
- When no human review, toggle not shown (current behavior)

---

## Where Toggle State Lives

In `EvalsView.tsx`: `const [metricsSource, setMetricsSource] = useState<'ai' | 'human'>('ai')`.
Passed down to MetricsBar. Also used to select which metrics array to pass.

---

## Verification

- No human review: MetricsBar shows AI metrics, no toggle visible
- Human review exists: Toggle appears, defaults to AI
- Switch to Human: Metrics update to human-adjusted values
- Values make sense: if all accepted, human metrics should be >= AI metrics
- If some rejected, human metrics should be <= AI metrics
