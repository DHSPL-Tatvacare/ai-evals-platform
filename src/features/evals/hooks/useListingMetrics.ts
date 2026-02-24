import { useMemo } from 'react';
import {
  computeUploadFlowMetrics,
  computeApiFlowMetrics,
  computeHumanAdjustedUploadMetrics,
  computeHumanAdjustedApiMetrics,
  type MetricResult,
  getRating,
  getRatingForErrorRate,
} from '../metrics';
import type {
  Listing,
  AIEvaluation,
  TranscriptData,
  HumanReview,
  SegmentReviewItem,
  FieldReviewItem,
} from '@/types';

/**
 * Optional live working-state overrides.
 * When provided, metrics are computed from these maps instead of
 * humanReview.result?.items or pre-computed summary, enabling
 * live metrics updates as the user edits.
 */
interface WorkingReviewState {
  segmentReviews?: Map<number, SegmentReviewItem>;
  fieldReviews?: Map<string, FieldReviewItem>;
}

/**
 * Hook to compute metrics for a listing.
 * Returns a flat MetricResult[] suitable for MetricsBar, or null if
 * evaluation hasn't been run / hasn't completed yet.
 *
 * Upload flow → [Match, WER, CER]
 * API flow    → [Field Accuracy, Recall, Precision, WER, CER]
 *
 * When metricsSource='human' and humanReview exists, returns
 * human-adjusted metrics instead of AI-computed ones.
 *
 * When `workingState` is provided, live local edits are used
 * instead of saved humanReview data — this ensures the submit
 * payload contains metrics computed from current changes.
 */
export function useListingMetrics(
  listing: Listing | null,
  aiEval?: AIEvaluation | null,
  humanReview?: HumanReview | null,
  metricsSource?: 'ai' | 'human',
  workingState?: WorkingReviewState,
): MetricResult[] | null {
  return useMemo(() => {
    if (!aiEval || aiEval.status !== 'completed' || !aiEval.judgeOutput) return null;

    const isApi = aiEval.flowType === 'api';
    const hasWorkingState = !!workingState && (
      (isApi && workingState.fieldReviews && workingState.fieldReviews.size > 0) ||
      (!isApi && workingState.segmentReviews && workingState.segmentReviews.size > 0)
    );
    const wantHuman = metricsSource === 'human' && (hasWorkingState || !!humanReview);

    // --- Human-adjusted metrics ---
    if (wantHuman) {
      // When live working state is available, always compute from it
      // (skip the saved summary shortcut — it would be stale)
      if (!hasWorkingState) {
        // Shortcut: use pre-computed adjustedMetrics from summary if available
        const adjusted = humanReview?.summary?.adjustedMetrics;
        if (adjusted && Object.keys(adjusted).length > 0) {
          return buildMetricsFromSummary(adjusted, isApi);
        }
      }

      if (isApi) {
        const apiTranscript = listing?.apiResponse?.input || '';
        const judgeTranscript = aiEval.judgeOutput.transcript || '';
        const fieldCritiques = aiEval.critique?.fieldCritiques ?? [];
        if (!apiTranscript && !judgeTranscript) return null;

        // Prefer live working maps; fall back to saved review items
        let fieldReviews: Map<string, FieldReviewItem>;
        if (hasWorkingState && workingState!.fieldReviews) {
          fieldReviews = workingState!.fieldReviews;
        } else {
          fieldReviews = new Map<string, FieldReviewItem>();
          const items = humanReview?.result?.items ?? [];
          for (const item of items) {
            if ('fieldPath' in item) {
              fieldReviews.set(item.fieldPath, item as FieldReviewItem);
            }
          }
        }

        return computeHumanAdjustedApiMetrics(
          apiTranscript,
          judgeTranscript,
          fieldCritiques,
          fieldReviews,
        );
      }

      // Upload flow
      if (!listing?.transcript) return null;
      const judgeTranscriptData = {
        fullTranscript: aiEval.judgeOutput.transcript,
        segments: aiEval.judgeOutput.segments ?? [],
      } as unknown as TranscriptData;

      // Prefer live working maps; fall back to saved review items
      let segmentReviews: Map<number, SegmentReviewItem>;
      if (hasWorkingState && workingState!.segmentReviews) {
        segmentReviews = workingState!.segmentReviews;
      } else {
        segmentReviews = new Map<number, SegmentReviewItem>();
        const items = humanReview?.result?.items ?? [];
        for (const item of items) {
          if ('segmentIndex' in item) {
            segmentReviews.set(item.segmentIndex, item as SegmentReviewItem);
          }
        }
      }

      return computeHumanAdjustedUploadMetrics(
        listing.transcript,
        judgeTranscriptData,
        segmentReviews,
      );
    }

    // --- Standard AI metrics ---
    if (isApi) {
      const apiTranscript = listing?.apiResponse?.input || '';
      const judgeTranscript = aiEval.judgeOutput.transcript || '';
      const fieldCritiques = aiEval.critique?.fieldCritiques ?? [];

      if (!apiTranscript && !judgeTranscript) return null;

      return computeApiFlowMetrics(apiTranscript, judgeTranscript, fieldCritiques);
    }

    // Upload flow: segment-based transcripts
    if (!listing?.transcript) return null;

    const judgeTranscriptData = {
      fullTranscript: aiEval.judgeOutput.transcript,
      segments: aiEval.judgeOutput.segments ?? [],
    } as unknown as TranscriptData;

    return computeUploadFlowMetrics(listing.transcript, judgeTranscriptData);
  }, [listing, aiEval, humanReview, metricsSource, workingState]);
}

/**
 * Build MetricResult[] directly from pre-computed adjustedMetrics summary.
 * Keys match metric IDs: match, wer, cer, fieldAccuracy, extractionRecall, extractionPrecision.
 */
function buildMetricsFromSummary(
  adjusted: Record<string, number>,
  isApi: boolean,
): MetricResult[] {
  const base: MetricResult[] = isApi
    ? buildApiMetricsFromValues(adjusted)
    : buildUploadMetricsFromValues(adjusted);

  // All summary-sourced metrics are human-adjusted
  return base.map(m => ({ ...m, source: 'human' as const }));
}

function buildApiMetricsFromValues(v: Record<string, number>): MetricResult[] {
  const accuracy = v.fieldAccuracy ?? 0;
  const recall = v.extractionRecall ?? 0;
  const precision = v.extractionPrecision ?? 0;
  const werVal = v.wer ?? 0;
  const cerVal = v.cer ?? 0;

  return [
    {
      id: 'fieldAccuracy',
      label: 'Field Accuracy',
      value: accuracy,
      displayValue: `${accuracy.toFixed(1)}%`,
      maxValue: 100,
      percentage: accuracy,
      rating: getRating(accuracy),
      description: 'Human-adjusted field accuracy',
    },
    {
      id: 'extractionRecall',
      label: 'Recall',
      value: recall,
      displayValue: `${recall.toFixed(1)}%`,
      maxValue: 100,
      percentage: recall,
      rating: getRating(recall),
      description: 'Extraction recall',
    },
    {
      id: 'extractionPrecision',
      label: 'Precision',
      value: precision,
      displayValue: `${precision.toFixed(1)}%`,
      maxValue: 100,
      percentage: precision,
      rating: getRating(precision),
      description: 'Human-adjusted precision',
    },
    {
      id: 'wer',
      label: 'WER',
      value: werVal,
      displayValue: werVal.toFixed(2),
      maxValue: 1,
      percentage: (1 - werVal) * 100,
      rating: getRatingForErrorRate(werVal),
      description: 'Word Error Rate',
    },
    {
      id: 'cer',
      label: 'CER',
      value: cerVal,
      displayValue: cerVal.toFixed(2),
      maxValue: 1,
      percentage: (1 - cerVal) * 100,
      rating: getRatingForErrorRate(cerVal),
      description: 'Character Error Rate',
    },
  ];
}

function buildUploadMetricsFromValues(v: Record<string, number>): MetricResult[] {
  const werVal = v.wer ?? 0;
  const cerVal = v.cer ?? 0;
  const matchVal = v.match ?? (100 - werVal * 100);

  return [
    {
      id: 'match',
      label: 'Match',
      value: matchVal,
      displayValue: `${matchVal.toFixed(1)}%`,
      maxValue: 100,
      percentage: matchVal,
      rating: getRating(matchVal),
      description: 'Human-adjusted match',
    },
    {
      id: 'wer',
      label: 'WER',
      value: werVal,
      displayValue: werVal.toFixed(2),
      maxValue: 1,
      percentage: (1 - werVal) * 100,
      rating: getRatingForErrorRate(werVal),
      description: 'Word Error Rate',
    },
    {
      id: 'cer',
      label: 'CER',
      value: cerVal,
      displayValue: cerVal.toFixed(2),
      maxValue: 1,
      percentage: (1 - cerVal) * 100,
      rating: getRatingForErrorRate(cerVal),
      description: 'Character Error Rate',
    },
  ];
}
