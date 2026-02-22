/**
 * Compute evaluation metrics for both upload and API flows.
 *
 * Each function returns a flat MetricResult[] — the MetricsBar
 * component renders whatever array it receives, with no knowledge
 * of flow types.
 */

import { getRating, type MetricResult } from './types';
import { calculateWERMetric, calculateCERMetric } from './wordErrorRate';
import type { TranscriptData, FieldCritique } from '@/types';

/**
 * Convert transcript to plain text for comparison
 */
function transcriptToText(transcript: TranscriptData): string {
  return transcript.segments.map(s => s.text).join(' ');
}

/**
 * Calculate simple match metric from WER (100 - WER)
 */
function calculateMatchMetric(wer: MetricResult): MetricResult {
  const percentage = Math.max(0, 100 - wer.value);

  return {
    id: 'match',
    label: 'Match',
    value: percentage,
    displayValue: `${percentage.toFixed(1)}%`,
    maxValue: 100,
    percentage,
    rating: getRating(percentage),
    description: 'Overall transcript similarity (100 - WER)',
    tooltip: 'How similar the original and judge transcripts are.\n100% − WER',
  };
}

/**
 * Upload flow: segment-based transcript comparison.
 * Returns [Match, WER, CER].
 */
export function computeUploadFlowMetrics(
  originalTranscript: TranscriptData,
  judgeTranscript: TranscriptData,
): MetricResult[] {
  const originalText = transcriptToText(originalTranscript);
  const llmText = transcriptToText(judgeTranscript);

  const wer = calculateWERMetric(originalText, llmText);
  const cer = calculateCERMetric(originalText, llmText);
  const match = calculateMatchMetric(wer);

  return [match, wer, cer];
}

/**
 * API flow: field-level accuracy + transcript WER/CER.
 * Returns [Field Accuracy, Recall, Precision, WER, CER].
 */
export function computeApiFlowMetrics(
  apiTranscript: string,
  judgeTranscript: string,
  fieldCritiques: FieldCritique[],
): MetricResult[] {
  // Transcript metrics (WER/CER on full strings)
  const wer = calculateWERMetric(apiTranscript, judgeTranscript);
  const cer = calculateCERMetric(apiTranscript, judgeTranscript);

  // Field Accuracy
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
    description: `${matchCount}/${total} fields match`,
    tooltip: 'Percentage of compared fields where API and judge agree.\nMatched fields ÷ total fields × 100',
  };

  // Extraction Recall
  const apiExtracted = fieldCritiques.filter(
    fc => String(fc.apiValue) !== '(not found)',
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
    description: `${apiExtracted}/${total} items captured`,
    tooltip: 'Of everything the judge identified, how much did the API also extract?\nExtracted items ÷ total items × 100',
  };

  // Extraction Precision
  const apiCorrect = fieldCritiques.filter(
    fc => String(fc.apiValue) !== '(not found)' && fc.match,
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
    description: `${apiCorrect}/${apiExtracted} extracted values correct`,
    tooltip: 'Of everything the API extracted, how much was correct?\nCorrect extractions ÷ total extractions × 100',
  };

  return [fieldAccuracy, extractionRecall, extractionPrecision, wer, cer];
}
