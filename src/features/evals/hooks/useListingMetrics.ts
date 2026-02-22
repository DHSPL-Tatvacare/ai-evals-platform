import { useMemo } from 'react';
import { computeUploadFlowMetrics, computeApiFlowMetrics, type MetricResult } from '../metrics';
import type { Listing, AIEvaluation, TranscriptData } from '@/types';

/**
 * Hook to compute metrics for a listing.
 * Returns a flat MetricResult[] suitable for MetricsBar, or null if
 * evaluation hasn't been run / hasn't completed yet.
 *
 * Upload flow → [Match, WER, CER]
 * API flow    → [Field Accuracy, Recall, Precision, WER, CER]
 */
export function useListingMetrics(
  listing: Listing | null,
  aiEval?: AIEvaluation | null,
): MetricResult[] | null {
  return useMemo(() => {
    if (!aiEval || aiEval.status !== 'completed' || !aiEval.judgeOutput) return null;

    if (aiEval.flowType === 'api') {
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
  }, [listing?.transcript, listing?.apiResponse, aiEval]);
}
