# Phase 02 — Types and API Client

## Type Changes (`src/types/eval.types.ts`)

### Remove (lines 165-180)
- `TranscriptCorrection` interface
- `HumanEvaluation` interface

### Replace with

```typescript
// === HUMAN REVIEW TYPES ===

export type ReviewVerdict = 'accept' | 'reject' | 'correct';
export type OverallVerdict = 'accepted' | 'rejected' | 'accepted_with_corrections';
export type ReviewSchema = 'segment_review' | 'field_review' | 'thread_review';

/** A single segment-level review item (upload flow) */
export interface SegmentReviewItem {
  segmentIndex: number;
  verdict: ReviewVerdict;
  correctedText?: string | null;
  comment?: string | null;
}

/** A single field-level review item (API flow) */
export interface FieldReviewItem {
  fieldPath: string;
  verdict: ReviewVerdict;
  correctedValue?: unknown;
  comment?: string | null;
}

/** A single thread-level review item (kaira future) */
export interface ThreadReviewItem {
  threadId: string;
  evaluatorType: string;
  originalVerdict: string;
  humanVerdict: string;
  comment?: string | null;
}

/** Union of all review item types */
export type ReviewItem = SegmentReviewItem | FieldReviewItem | ThreadReviewItem;

/** The result JSONB stored in eval_runs.result for human reviews */
export interface HumanReviewResult {
  overallVerdict: OverallVerdict;
  notes: string;
  items: ReviewItem[];
}

/** The summary JSONB stored in eval_runs.summary for human reviews */
export interface HumanReviewSummary {
  totalItems: number;
  accepted: number;
  rejected: number;
  corrected: number;
  unreviewed: number;
  overallVerdict: OverallVerdict;
  adjustedMetrics: Record<string, number>;
}

/** Frontend representation of a saved human review (parsed from EvalRun) */
export interface HumanReview {
  id: string;
  aiEvalRunId: string;
  reviewSchema: ReviewSchema;
  result: HumanReviewResult;
  summary: HumanReviewSummary;
  createdAt: string;
  completedAt?: string;
}
```

**Keep** `HumanEvalStatus` type (line 3) — rename to keep backward compat or remove if unused elsewhere.

## API Client Additions (`src/services/api/evalRunsApi.ts`)

Add 3 methods:

```typescript
/** Fetch the human review linked to an AI eval run */
export async function fetchHumanReview(aiRunId: string): Promise<HumanReview | null> {
  const data = await apiRequest(`/api/eval-runs/${aiRunId}/human-review`);
  if (!data) return null;
  return parseHumanReview(data);
}

/** Create or update the human review for an AI eval run */
export async function upsertHumanReview(
  aiRunId: string,
  payload: { reviewSchema: string; result: HumanReviewResult; summary: HumanReviewSummary }
): Promise<HumanReview> {
  const data = await apiRequest(`/api/eval-runs/${aiRunId}/human-review`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
  return parseHumanReview(data);
}

/** Delete the human review for an AI eval run */
export async function deleteHumanReview(aiRunId: string): Promise<void> {
  const review = await fetchHumanReview(aiRunId);
  if (review) {
    await deleteEvalRun(review.id);
  }
}
```

### Helper (same file)

```typescript
function parseHumanReview(data: Record<string, unknown>): HumanReview {
  return {
    id: data.id as string,
    aiEvalRunId: ((data.config as Record<string, unknown>)?.aiEvalRunId ?? '') as string,
    reviewSchema: ((data.config as Record<string, unknown>)?.reviewSchema ?? 'segment_review') as ReviewSchema,
    result: data.result as HumanReviewResult,
    summary: data.summary as HumanReviewSummary,
    createdAt: data.createdAt as string,
    completedAt: data.completedAt as string | undefined,
  };
}
```

## Verification

- TypeScript compiles: `npx tsc -b`
- Import new types in existing components without errors
- API methods callable from hook
