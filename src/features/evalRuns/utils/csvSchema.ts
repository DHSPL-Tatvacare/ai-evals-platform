/**
 * Batch-eval CSV schema built on the shared CSV import utility.
 *
 * The required fields mirror `ChatMessage.from_csv_row` in
 * backend/app/services/evaluators/models.py — keep in sync.
 */

import type {
  ColumnMapping,
  CsvFieldDef as SharedCsvFieldDef,
  CsvPreviewResult,
  HeaderValidation,
} from '@/features/csvImport/types';
import {
  getAllFieldNames,
  getRequiredFieldNames,
  parseCsvPreview as parseSharedCsvPreview,
  remapCsvContent as remapSharedCsvContent,
  validateCsvHeaders as validateSharedCsvHeaders,
} from '@/features/csvImport/utils';

export type CsvFieldDef = SharedCsvFieldDef<'identity' | 'content' | 'metadata'>;
export type { ColumnMapping, CsvPreviewResult, HeaderValidation };

export const CSV_FIELD_SCHEMA: CsvFieldDef[] = [
  // Identity group — how messages are grouped and attributed
  { name: 'thread_id',    description: 'Conversation thread identifier',    required: true,  example: 'thr_abc123',           group: 'identity' },
  { name: 'user_id',      description: 'User who sent the message',         required: true,  example: 'usr_xyz789',           group: 'identity' },
  { name: 'session_id',   description: 'Session identifier',                required: true,  example: 'sess_001',             group: 'identity' },
  { name: 'response_id',  description: 'Unique response identifier',        required: false, example: 'resp_456',             group: 'identity' },

  // Content group — the actual conversation data being evaluated
  { name: 'query_text',              description: 'User message / query',              required: true, example: 'Log 2 eggs for breakfast', group: 'content' },
  { name: 'final_response_message',  description: 'Bot response to the query',         required: true, example: 'Logged: 2 eggs (140 kcal)', group: 'content' },
  { name: 'intent_detected',         description: 'Detected intent classification',    required: true, example: 'log_meal',                  group: 'content' },
  { name: 'intent_query_type',       description: 'Sub-type of the detected intent',   required: false, example: 'food_logging',             group: 'content' },

  // Metadata group — timestamps and flags
  { name: 'timestamp',     description: 'ISO 8601 timestamp of the message', required: true,  example: '2025-01-15T10:30:00Z', group: 'metadata' },
  { name: 'has_image',     description: 'Whether message contains an image (0 or 1)', required: true, example: '0', group: 'metadata' },
  { name: 'error_message', description: 'Error message if the response failed', required: false, example: '',  group: 'metadata' },
];

export const REQUIRED_FIELDS = getRequiredFieldNames(CSV_FIELD_SCHEMA);
export const ALL_FIELD_NAMES = getAllFieldNames(CSV_FIELD_SCHEMA);

export function parseCsvPreview(text: string, maxRows = 10): CsvPreviewResult {
  return parseSharedCsvPreview(text, maxRows);
}

export function validateCsvHeaders(headers: string[]): HeaderValidation {
  return validateSharedCsvHeaders(headers, CSV_FIELD_SCHEMA);
}

export function remapCsvContent(text: string, mapping: ColumnMapping): string {
  return remapSharedCsvContent(text, mapping);
}
