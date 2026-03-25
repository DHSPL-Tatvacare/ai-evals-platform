import { apiRequest } from './client';

// ── Types ──────────────────────────────────────────────────────────────────

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
}

export interface LeadListResponse {
  leads: LeadListRecord[];
  total: number;
  page: number;
  pageSize: number;
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
}

// ── API functions ──────────────────────────────────────────────────────────

export interface LeadFilters {
  dateFrom: string;
  dateTo: string;
  agents: string[];
  stage: string[];
  mqlMin: string;
  condition: string[];
  city: string[];
  prospectId: string;
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
  if (filters.agents.length > 0) params.set('agents', filters.agents.join(','));
  if (filters.stage.length > 0) params.set('stage', filters.stage.join(','));
  if (filters.mqlMin) params.set('mql_min', filters.mqlMin);
  if (filters.condition.length > 0) params.set('condition', filters.condition.join(','));
  if (filters.city.length > 0) params.set('city', filters.city.join(','));
  if (filters.prospectId) params.set('prospect_id', filters.prospectId);

  return apiRequest<LeadListResponse>(`/api/inside-sales/leads?${params.toString()}`);
}

export async function fetchLeadDetail(prospectId: string): Promise<LeadDetailFullResponse> {
  return apiRequest<LeadDetailFullResponse>(`/api/inside-sales/leads/${prospectId}/detail`);
}
