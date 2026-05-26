import type { CallSelectionConfig } from './SelectCallsStep';

export interface CallQualitySelection {
  agents: string[];
  lead_ids: string[];
  direction: 'inbound' | 'outbound' | null;
  status: string | null;
  event_codes: number[];
  duration_min_seconds: number | null;
  duration_max_seconds: number | null;
  has_recording: 'only' | 'any';
  call_date_from: string | null;
  call_date_to: string | null;
  mode: CallSelectionConfig['selectionMode'];
  sample_size: number | null;
  selected_ids: string[];
  skip_evaluated: boolean;
  skip_evaluated_scope: 'self';
}

function parseDuration(v: string): number | null {
  const n = parseInt(v, 10);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

/** Builds the EvaluationSelectionSpec the backend expects (Pydantic
 *  extra='forbid'). Empty strings → null; date inputs already emit
 *  YYYY-MM-DD so they pass through unchanged. */
export function buildCallQualitySelection(config: CallSelectionConfig): CallQualitySelection {
  const eventCodesList = config.eventCodes
    .split(',')
    .map((s) => parseInt(s.trim(), 10))
    .filter((n) => Number.isFinite(n));
  const hasRecordingMode: 'only' | 'any' = config.hasRecording ? 'only' : 'any';
  // Floor toggle ⇒ effective duration_min_seconds = 10 unless the user
  // already set a higher explicit floor.
  const explicitMin = parseDuration(config.durationMin);
  const effectiveDurationMin = config.minDuration
    ? Math.max(10, explicitMin ?? 10)
    : explicitMin;

  return {
    agents: config.agents,
    lead_ids: config.leadId,
    direction: (config.direction || null) as 'inbound' | 'outbound' | null,
    status: config.status || null,
    event_codes: eventCodesList,
    duration_min_seconds: effectiveDurationMin,
    duration_max_seconds: parseDuration(config.durationMax),
    has_recording: hasRecordingMode,
    call_date_from: config.callDateFrom || null,
    call_date_to: config.callDateTo || null,
    mode: config.selectionMode,
    sample_size: config.selectionMode === 'sample' ? config.sampleSize : null,
    selected_ids: config.selectionMode === 'specific' ? config.selectedCallIds : [],
    skip_evaluated: config.skipEvaluated,
    skip_evaluated_scope: 'self',
  };
}
