import { expect, test } from 'vitest';
import { buildInsideSalesSelection } from './buildInsideSalesSelection';
import type { CallSelectionConfig } from './SelectCallsStep';

const BASE_CONFIG: CallSelectionConfig = {
  agents: [],
  leadId: [],
  direction: '',
  status: '',
  durationMin: '',
  durationMax: '',
  hasRecording: false,
  eventCodes: '',
  callDateFrom: '',
  callDateTo: '',
  selectionMode: 'all',
  sampleSize: 20,
  selectedCallIds: [],
  skipEvaluated: true,
  minDuration: true,
};

test('maps callConfig dates into selection.call_date_from / call_date_to', () => {
  const selection = buildInsideSalesSelection({
    ...BASE_CONFIG,
    callDateFrom: '2026-03-01',
    callDateTo: '2026-03-31',
  });
  expect(selection.call_date_from).toBe('2026-03-01');
  expect(selection.call_date_to).toBe('2026-03-31');
});

test('emits null for unset call dates', () => {
  const selection = buildInsideSalesSelection(BASE_CONFIG);
  expect(selection.call_date_from).toBeNull();
  expect(selection.call_date_to).toBeNull();
});
