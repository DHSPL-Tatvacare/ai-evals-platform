import { apiRequest } from './client';

// ── Types ──────────────────────────────────────────────────────────────────

export interface LeadPlanPurchase {
  planName: string | null;
  durationOrQuantity: string | null;
  programPrice: string | null;
  invoiceAmount: string | null;
  paymentId: string | null;
  paymentDateAndTime: string | null;
  planAssignedAt: string | null;
  signUpDate: string | null;
  programStartDate: string | null;
  programEndDate: string | null;
  planIncludesCgm: string | null;
  cgm: string | null;
  cgmBrand: string | null;
  sensorCount: string | null;
  transmitterCount: string | null;
  bcaDevice: string | null;
  nutraceuticalsSold: string | null;
  salesTeam: string | null;
  deviceAwbNumber: string | null;
  leadConversionDate: string | null;
}

export interface LeadListRecord {
  prospectId: string;
  firstName: string;
  lastName: string | null;
  phone: string;
  prospectStage: string;
  city: string | null;
  ageGroup: string | null;
  condition: string | null;
  hba1cBand: string | null;
  intentToPay: string | null;
  agentName: string | null;
  rnrCount: number;
  answeredCount: number;
  totalDials: number;
  connectRate: number | null;
  frtSeconds: number | null;
  leadAgeDays: number;
  daysSinceLastContact: number | null;
  mqlScore: number;
  mqlSignals: Record<string, boolean>;
  createdOn: string;
  lastActivityOn: string | null;
  source: string | null;
  sourceCampaign: string | null;
  planName: string | null;
  plan: LeadPlanPurchase;
}

export interface LeadListResponse {
  leads: LeadListRecord[];
  total: number;
  page: number;
  pageSize: number;
  freshness: CollectionFreshness;
}

export interface CallRecord {
  activityId: string;
  prospectId: string;
  agentName: string;
  agentEmail: string;
  eventCode: number;
  direction: 'inbound' | 'outbound';
  status: string;
  callStartTime: string;
  durationSeconds: number;
  recordingUrl: string;
  phoneNumber: string;
  displayNumber: string;
  callNotes: string;
  callSessionId: string;
  createdOn: string;
  lastEvalScore?: number;
  evalCount?: number;
}

export interface CallListResponse {
  calls: CallRecord[];
  total: number;
  page: number;
  pageSize: number;
  freshness: CollectionFreshness;
}

export interface CollectionFreshness {
  lastSyncedAt: string | null;
  syncInProgress: boolean;
  stale: boolean;
}

export interface CallFilters {
  dateFrom: string;
  dateTo: string;
  agents: string[];
  /** Multi-select via the suggestions endpoint; CSV-joined on the wire. */
  prospectId: string[];
  direction: string;
  status: string;
  hasRecording: boolean;
  eventCodes: string;
  durationMin: string;
  durationMax: string;
}

export interface LeadCallRecord {
  activityId: string;
  callTime: string;
  agentName: string | null;
  durationSeconds: number;
  status: string;
  recordingUrl: string | null;
  evalScore: number | null;
  isCounseling: boolean;
}

export interface LeadEvalHistoryEntry {
  id: string;
  threadId: string;
  runId: string;
  result: Record<string, unknown>;
  createdAt: string;
}

export interface LeadDetailFullResponse {
  prospectId: string;
  firstName: string;
  lastName: string | null;
  phone: string;
  email: string | null;
  prospectStage: string;
  city: string | null;
  ageGroup: string | null;
  condition: string | null;
  hba1cBand: string | null;
  bloodSugarBand: string | null;
  diabetesDuration: string | null;
  currentManagement: string | null;
  goal: string | null;
  intentToPay: string | null;
  jobTitle: string | null;
  preferredCallTime: string | null;
  agentName: string | null;
  source: string | null;
  sourceCampaign: string | null;
  createdOn: string;
  mqlScore: number;
  mqlSignals: Record<string, boolean>;
  frtSeconds: number | null;
  totalDials: number;
  connectRate: number | null;
  counselingCount: number;
  counselingRate: number | null;
  callbackAdherenceSeconds: number | null;
  leadAgeDays: number;
  daysSinceLastContact: number | null;
  callHistory: LeadCallRecord[];
  historyTruncated: boolean;
  evalHistory: LeadEvalHistoryEntry[];
  plan: LeadPlanPurchase;
}

// ── API functions ──────────────────────────────────────────────────────────

export interface LeadFilters {
  dateFrom: string;
  dateTo: string;
  /** Multi-select via the suggestions endpoint; CSV-joined on the wire. */
  agents: string[];
  stage: string[];
  mqlMin: string;
  condition: string[];
  /** Multi-select via the suggestions endpoint; CSV-joined on the wire. */
  city: string[];
  /** Multi-select via the suggestions endpoint; CSV-joined on the wire. */
  prospectId: string[];
  /** Multi-select via the suggestions endpoint; CSV-joined on the wire. */
  phone: string[];
  /** Multi-select via the suggestions endpoint; CSV-joined on the wire. */
  planName: string[];
  q: string;
}

export type CallQueryScope = 'page' | 'all';
export type InsideSalesCollectionFamily = 'calls' | 'leads';

export interface CollectionRefreshResponse {
  jobId: string;
  sourceFamily: InsideSalesCollectionFamily;
  syncMode: string;
  status: string;
}

export interface CollectionCoverage {
  hasData: boolean;
  availableFrom: string | null;
  availableTo: string | null;
  lastScheduledSyncAt: string | null;
  lastScheduledSyncStatus: string | null;
}

export interface CollectionSyncStatus {
  lastSuccessAt: string | null;
  lastAttemptAt: string | null;
  lastStatus: 'running' | 'completed' | 'failed' | 'cancelled' | null;
  lastError: string | null;
  syncInProgress: boolean;
}

export async function fetchCollectionStatus(
  sourceFamily: InsideSalesCollectionFamily,
): Promise<CollectionSyncStatus> {
  return apiRequest<CollectionSyncStatus>(
    `/api/inside-sales/collections/${encodeURIComponent(sourceFamily)}/status`,
  );
}

export type SuggestionField =
  | 'prospect_id'
  | 'phone'
  | 'agent_name'
  | 'city'
  | 'stage'
  | 'plan_name';

export async function fetchCollectionSuggestions(
  sourceFamily: InsideSalesCollectionFamily,
  field: SuggestionField,
  q: string,
  limit = 20,
): Promise<string[]> {
  const params = new URLSearchParams({ field, limit: String(limit) });
  const trimmed = (q ?? '').trim();
  if (trimmed) params.set('q', trimmed);
  const res = await apiRequest<{ values: string[] }>(
    `/api/inside-sales/collections/${encodeURIComponent(sourceFamily)}/suggestions?${params.toString()}`,
  );
  return res.values ?? [];
}

export async function fetchCoverage(
  sourceFamily: InsideSalesCollectionFamily,
): Promise<CollectionCoverage> {
  return apiRequest<CollectionCoverage>(
    `/api/inside-sales/coverage?source_family=${encodeURIComponent(sourceFamily)}`,
  );
}

function parseCoverageDate(value: string | null | undefined): number | null {
  const trimmed = (value ?? '').trim();
  if (!trimmed) {
    return null;
  }
  const normalized = trimmed.includes('T') ? trimmed : `${trimmed.replace(' ', 'T')}Z`;
  const parsed = new Date(normalized).getTime();
  return Number.isNaN(parsed) ? null : parsed;
}

export function isRangeOutsideCoverage(
  coverage: CollectionCoverage | null,
  dateFrom: string,
  dateTo: string,
): boolean {
  const fromMs = parseCoverageDate(dateFrom);
  const toMs = parseCoverageDate(dateTo);
  const availableFromMs = parseCoverageDate(coverage?.availableFrom);
  const availableToMs = parseCoverageDate(coverage?.availableTo);

  if (
    !coverage
    || !coverage.hasData
    || fromMs === null
    || toMs === null
    || availableFromMs === null
    || availableToMs === null
  ) {
    return true;
  }

  return fromMs < availableFromMs || toMs > availableToMs;
}

export type CollectionRefreshSyncMode = 'incremental' | 'date_range' | 'bootstrap';

function buildCallSearchParams(
  filters: CallFilters,
  page: number,
  pageSize: number,
  scope: CallQueryScope,
): URLSearchParams {
  const params = new URLSearchParams({
    date_from: filters.dateFrom,
    date_to: filters.dateTo,
    page: String(page),
    page_size: String(pageSize),
  });

  if (scope !== 'page') {
    params.set('scope', scope);
  }
  if (filters.agents && filters.agents.length > 0) params.set('agents', filters.agents.join(','));
  if (filters.prospectId && filters.prospectId.length > 0) params.set('prospect_id', filters.prospectId.join(','));
  if (filters.direction) params.set('direction', filters.direction);
  if (filters.status) params.set('status', filters.status);
  if (filters.hasRecording) params.set('has_recording', 'true');
  if (filters.durationMin) params.set('duration_min', filters.durationMin);
  if (filters.durationMax) params.set('duration_max', filters.durationMax);
  if (filters.eventCodes) params.set('event_codes', filters.eventCodes);

  return params;
}

export async function fetchCalls(
  filters: CallFilters,
  page: number,
  pageSize: number,
  options?: { scope?: CallQueryScope },
): Promise<CallListResponse> {
  const scope = options?.scope ?? 'page';
  const params = buildCallSearchParams(filters, page, pageSize, scope);
  return apiRequest<CallListResponse>(`/api/inside-sales/calls?${params.toString()}`);
}

export async function fetchCallsForSelection(
  filters: CallFilters,
  pageSize = 500,
): Promise<CallListResponse> {
  return fetchCalls(filters, 1, pageSize, { scope: 'all' });
}

export async function fetchLeads(
  filters: LeadFilters,
  page: number,
  pageSize: number,
): Promise<LeadListResponse> {
  const params = new URLSearchParams({
    date_from: filters.dateFrom,
    date_to: filters.dateTo,
    page: String(page),
    page_size: String(pageSize),
  });
  const q = (filters.q ?? '').trim();
  if (filters.agents && filters.agents.length > 0) params.set('agents', filters.agents.join(','));
  if (filters.stage && filters.stage.length > 0) params.set('stage', filters.stage.join(','));
  if (filters.mqlMin) params.set('mql_min', filters.mqlMin);
  if (filters.condition && filters.condition.length > 0) params.set('condition', filters.condition.join(','));
  if (filters.city && filters.city.length > 0) params.set('city', filters.city.join(','));
  if (filters.prospectId && filters.prospectId.length > 0) params.set('prospect_id', filters.prospectId.join(','));
  if (filters.phone && filters.phone.length > 0) params.set('phone', filters.phone.join(','));
  if (filters.planName && filters.planName.length > 0) params.set('plan_name', filters.planName.join(','));
  if (q) params.set('q', q);

  return apiRequest<LeadListResponse>(`/api/inside-sales/leads?${params.toString()}`);
}

export async function fetchLeadDetail(
  prospectId: string,
  options?: { refresh?: boolean },
): Promise<LeadDetailFullResponse> {
  const qs = options?.refresh ? '?refresh=true' : '';
  return apiRequest<LeadDetailFullResponse>(`/api/inside-sales/leads/${prospectId}/detail${qs}`);
}

export async function refreshInsideSalesCollection(
  sourceFamily: InsideSalesCollectionFamily,
  payload: {
    syncMode?: CollectionRefreshSyncMode;
    dateFrom?: string;
    dateTo?: string;
    eventCodes?: string;
    overlapMinutes?: number;
  },
): Promise<CollectionRefreshResponse> {
  return apiRequest<CollectionRefreshResponse>(`/api/inside-sales/collections/${sourceFamily}/refresh`, {
    method: 'POST',
    body: JSON.stringify({
      syncMode: payload.syncMode,
      dateFrom: payload.dateFrom,
      dateTo: payload.dateTo,
      eventCodes: payload.eventCodes,
      overlapMinutes: payload.overlapMinutes,
    }),
  });
}
