import { beforeEach, expect, test, vi } from 'vitest';

const { apiRequestMock } = vi.hoisted(() => ({
  apiRequestMock: vi.fn(),
}));

vi.mock('./client', () => ({
  apiRequest: apiRequestMock,
}));

import { fetchCalls, fetchLeads } from './insideSales';
import type { CallFilters, LeadFilters } from './insideSales';

const EMPTY_CALL_FILTERS: CallFilters = {
  agents: [],
  leadId: [],
  direction: '',
  status: '',
  hasRecording: false,
  eventCodes: '',
  durationMin: '',
  durationMax: '',
  callDateFrom: '',
  callDateTo: '',
};

const EMPTY_LEAD_FILTERS: LeadFilters = {
  agents: [],
  stage: [],
  mqlMin: '',
  condition: [],
  city: [],
  leadId: [],
  phone: [],
  planName: [],
  q: '',
  leadCreatedFrom: '',
  leadCreatedTo: '',
};

function calledUrl(): string {
  return apiRequestMock.mock.calls[0][0] as string;
}

beforeEach(() => {
  apiRequestMock.mockReset();
  apiRequestMock.mockResolvedValue({ calls: [], leads: [], total: 0, page: 1, pageSize: 50, freshness: null });
});

test('buildCallSearchParams sends call_date_from / call_date_to when set', async () => {
  await fetchCalls(
    { ...EMPTY_CALL_FILTERS, callDateFrom: '2026-01-01', callDateTo: '2026-01-31' },
    1,
    50,
  );
  const url = calledUrl();
  expect(url).toContain('call_date_from=2026-01-01');
  expect(url).toContain('call_date_to=2026-01-31');
});

test('buildCallSearchParams omits date params when empty', async () => {
  await fetchCalls(EMPTY_CALL_FILTERS, 1, 50);
  const url = calledUrl();
  expect(url).not.toContain('call_date_from');
  expect(url).not.toContain('call_date_to');
});

test('fetchLeads sends lead_created_from / lead_created_to when set', async () => {
  await fetchLeads(
    { ...EMPTY_LEAD_FILTERS, leadCreatedFrom: '2026-02-01', leadCreatedTo: '2026-02-28' },
    1,
    50,
  );
  const url = calledUrl();
  expect(url).toContain('lead_created_from=2026-02-01');
  expect(url).toContain('lead_created_to=2026-02-28');
});

test('fetchLeads omits lead-created params when empty', async () => {
  await fetchLeads(EMPTY_LEAD_FILTERS, 1, 50);
  const url = calledUrl();
  expect(url).not.toContain('lead_created_from');
  expect(url).not.toContain('lead_created_to');
});
