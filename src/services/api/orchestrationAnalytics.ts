import { apiRequest } from './client';
import type {
  AnalyticsQueryParams,
  BreakdownDimension,
  OrchestrationBreakdown,
  OrchestrationOverview,
  OrchestrationRunDetail,
  OrchestrationRuns,
  OrchestrationSignals,
  RunReportResponse,
  TrendResponse,
} from '@/features/orchestration/analytics/types';

const BASE = '/api/orchestration/analytics';

function rangeParams(params: AnalyticsQueryParams): URLSearchParams {
  const q = new URLSearchParams({ appId: params.appId, scope: params.scope });
  if (params.from) q.set('from', params.from);
  if (params.to) q.set('to', params.to);
  return q;
}

export function fetchOverview(params: AnalyticsQueryParams): Promise<OrchestrationOverview> {
  return apiRequest<OrchestrationOverview>(`${BASE}/overview?${rangeParams(params).toString()}`);
}

export function fetchBreakdown(
  params: AnalyticsQueryParams & { dimension: BreakdownDimension },
): Promise<OrchestrationBreakdown> {
  const q = rangeParams(params);
  q.set('dimension', params.dimension);
  return apiRequest<OrchestrationBreakdown>(`${BASE}/breakdown?${q.toString()}`);
}

export function fetchRuns(
  params: AnalyticsQueryParams & { page?: number; pageSize?: number },
): Promise<OrchestrationRuns> {
  const q = rangeParams(params);
  if (params.page) q.set('page', String(params.page));
  if (params.pageSize) q.set('pageSize', String(params.pageSize));
  return apiRequest<OrchestrationRuns>(`${BASE}/runs?${q.toString()}`);
}

export function fetchRunDetail(
  runId: string,
  params: AnalyticsQueryParams & { page?: number; pageSize?: number },
): Promise<OrchestrationRunDetail> {
  const q = new URLSearchParams({ appId: params.appId, scope: params.scope });
  if (params.page) q.set('page', String(params.page));
  if (params.pageSize) q.set('pageSize', String(params.pageSize));
  return apiRequest<OrchestrationRunDetail>(
    `${BASE}/runs/${encodeURIComponent(runId)}?${q.toString()}`,
  );
}

export function fetchRunReport(
  runId: string,
  params: { appId: string; scope: AnalyticsQueryParams['scope'] },
): Promise<RunReportResponse> {
  const q = new URLSearchParams({ appId: params.appId, scope: params.scope });
  return apiRequest<RunReportResponse>(
    `${BASE}/runs/${encodeURIComponent(runId)}/report?${q.toString()}`,
  );
}

export function fetchTrend(params: AnalyticsQueryParams): Promise<TrendResponse> {
  return apiRequest<TrendResponse>(`${BASE}/trend?${rangeParams(params).toString()}`);
}

export function fetchSignals(params: {
  appId: string;
  scope: AnalyticsQueryParams['scope'];
}): Promise<OrchestrationSignals> {
  const q = new URLSearchParams({ appId: params.appId, scope: params.scope });
  return apiRequest<OrchestrationSignals>(`${BASE}/signals?${q.toString()}`);
}
