# Phase 05 — Orchestration

## EvalsView.tsx Rewire

### Current flow (lines 220-245)

- Tab "Human Review" renders `<HumanEvalNotepad listing={listing} aiEval={aiEval} />`

### New flow

- Tab "Human Review" renders the SAME comparison table as AI tab but with `reviewMode=true`
- Plus a `HumanReviewStatus` strip at top
- Plus a `MetricsBar` with human-adjusted metrics
- Plus a footer bar with "Submit Review" button and dirty indicator

### Human Review tab content structure

```tsx
<div className="flex flex-col h-full min-h-0 gap-4">
  {/* Status strip */}
  <HumanReviewStatus humanReview={humanReview} isDirty={isDirty} />

  {/* Metrics with toggle */}
  <MetricsBar
    metrics={currentMetrics}
    hasHumanReview={!!humanReview}
    metricsSource={metricsSource}
    onMetricsSourceChange={setMetricsSource}
  />

  {/* Same comparison table, review mode on */}
  {flowType === 'api' ? (
    <ApiEvalsView
      listing={listing}
      aiEval={aiEval}
      reviewMode={true}
      fieldReviews={fieldReviewsMap}
      onFieldReviewChange={handleFieldReviewChange}
    />
  ) : (
    <SegmentComparisonTable
      original={listing.transcript}
      llmGenerated={judgeTranscript}
      critique={aiEval.critique}
      audioFileId={listing.audioFile?.id}
      reviewMode={true}
      segmentReviews={segmentReviewsMap}
      onSegmentReviewChange={handleSegmentReviewChange}
    />
  )}

  {/* Submit footer */}
  <HumanReviewFooter
    isDirty={isDirty}
    isSubmitting={isSubmitting}
    reviewedCount={reviewedCount}
    totalCount={totalCount}
    overallVerdict={computedVerdict}
    onSubmit={handleSubmit}
    onDiscard={handleDiscard}
  />
</div>
```

**Note**: `HumanReviewFooter` is a simple inline div (not a separate file) — a sticky bottom bar with progress, verdict badge, and submit button. ~20 lines of JSX within EvalsView.

---

## HumanReviewStatus.tsx (New File)

Mirrors `AIEvalStatus.tsx` pattern (~80 lines). Horizontal strip showing:

```
[Status badge] | [Reviewed: N/M] | [Verdict badge] | [timestamp]
```

### Props

```typescript
interface HumanReviewStatusProps {
  humanReview: HumanReview | null;
  isDirty: boolean;
}
```

- **When no saved review**: "No review submitted" in muted text
- **When saved review exists**: Shows overall verdict badge, reviewed count, completed timestamp
- **When dirty**: Shows "Unsaved changes" indicator

---

## useHumanReview Hook (Full Rewrite of useHumanEvaluation.ts)

### New signature

```typescript
interface UseHumanReviewOptions {
  aiEvalRunId: string | undefined;
  flowType: FlowType;
  /** Total segment count (upload) or total field count (API) */
  totalItems: number;
}

interface UseHumanReviewReturn {
  /** Saved review from backend (null if none) */
  humanReview: HumanReview | null;
  /** Loading state */
  isLoading: boolean;
  /** Whether local state differs from saved */
  isDirty: boolean;
  /** Submit in progress */
  isSubmitting: boolean;
  /** Current review items map (local working copy) */
  reviewItems: Map<string | number, ReviewItem>;
  /** Update a single item */
  setReviewItem: (key: string | number, item: ReviewItem) => void;
  /** Remove a review for an item */
  clearReviewItem: (key: string | number) => void;
  /** Auto-computed from items */
  overallVerdict: OverallVerdict | null;
  /** Reviewed count */
  reviewedCount: number;
  /** Submit to backend */
  submit: (notes?: string) => Promise<void>;
  /** Discard local changes, revert to saved */
  discard: () => void;
}
```

### Implementation outline

1. **Fetch on mount**: `useEffect` calls `fetchHumanReview(aiEvalRunId)` → stores in `humanReview` state
2. **Initialize working copy**: `reviewItems` Map initialized from `humanReview.result.items` if exists, empty otherwise
3. **Dirty tracking**: Compare `reviewItems` against saved `humanReview.result.items` — `isDirty = true` if any difference
4. **setReviewItem**: Updates Map entry, triggers re-render, marks dirty
5. **overallVerdict**: `useMemo` — if no items reviewed, null. Else: any 'reject' → 'rejected', any 'correct' → 'accepted_with_corrections', all 'accept' → 'accepted'
6. **submit**:
   - Build `HumanReviewResult` from Map
   - Compute `HumanReviewSummary` (counts + adjustedMetrics)
   - Call `upsertHumanReview(aiEvalRunId, { reviewSchema, result, summary })`
   - Update `humanReview` state with response
   - `notificationService.success('Human review saved')`
   - Reset dirty state
7. **discard**: Reset `reviewItems` to saved state, clear dirty flag

### Dirty tracking pattern

Use a `useRef` to snapshot the saved items. Compare current Map against snapshot on each render (shallow compare of Map size + values). This reuses the `pendingChangesRef` pattern from the existing hook.

### adjustedMetrics computation on submit

Before calling upsert, compute metrics client-side using the human-adjusted compute functions. Store in summary so backend doesn't need to compute.

---

## Verdict Auto-Computation Logic

```typescript
function computeOverallVerdict(items: ReviewItem[]): OverallVerdict | null {
  if (items.length === 0) return null;
  const verdicts = items.map(i => i.verdict);
  if (verdicts.some(v => v === 'reject')) return 'rejected';
  if (verdicts.some(v => v === 'correct')) return 'accepted_with_corrections';
  return 'accepted';
}
```

---

## EvalsView Integration Changes

### What changes in EvalsView.tsx

1. **Import**: Remove `HumanEvalNotepad`, add `HumanReviewStatus`, add `useHumanReview`
2. **Hook call**: `const { humanReview, isDirty, ... } = useHumanReview({ aiEvalRunId: aiEval?.id, flowType, totalItems })`
3. **Metrics state**: `const [metricsSource, setMetricsSource] = useState<'ai' | 'human'>('ai')`
4. **Human tab content**: Replace `<HumanEvalNotepad>` with the table + footer structure described above
5. **MetricsBar**: Rendered inside both tabs, but the Human tab version has the toggle

### AI tab MetricsBar

- Check where MetricsBar is actually rendered. If in parent, the toggle needs to be wired through props or the MetricsBar moves inside EvalsView.
- Most likely: MetricsBar should be rendered INSIDE EvalsView for both tabs, with different configurations per tab.

---

## Verification

- Open listing with completed AI eval → Human Review tab shows same table with review columns
- Click Accept/Reject/Correct on segments → local state updates, dirty indicator shows
- Click Submit → API call fires, toast appears, dirty indicator clears
- Refresh page → review persists, columns populated from saved data
- Click Discard → reverts to saved state
- Verdict auto-computes: all accept → "Accepted" badge, mix → "Accepted with Corrections"
- Metrics toggle works in Human Review tab
