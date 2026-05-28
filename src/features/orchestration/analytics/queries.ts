/**
 * TanStack Query hooks for the orchestration analytics surface. Each hook wraps
 * the `orchestrationAnalytics` service (which calls `apiRequest`, inheriting the
 * 401-refresh-retry flow) and gates on `appId` so a missing app never fires a
 * request. Mirrors the `queries/runs.ts` pattern.
 */
import { useQuery } from '@tanstack/react-query';

import {
  fetchBreakdown,
  fetchOverview,
  fetchRunDetail,
  fetchRuns,
  fetchSignals,
} from '@/services/api/orchestrationAnalytics';
import type {
  AnalyticsQueryParams,
  BreakdownDimension,
  OrchestrationBreakdown,
  OrchestrationOverview,
  OrchestrationRunDetail,
  OrchestrationRuns,
  OrchestrationSignals,
} from './types';

const STALE_TIME_MS = 30_000;

export const analyticsQueryKeys = {
  overview: (p: AnalyticsQueryParams) =>
    ['orchestration', 'analytics', 'overview', p.appId, p.scope, p.from ?? null, p.to ?? null] as const,
  breakdown: (p: AnalyticsQueryParams, dimension: BreakdownDimension) =>
    ['orchestration', 'analytics', 'breakdown', dimension, p.appId, p.scope, p.from ?? null, p.to ?? null] as const,
  runs: (p: AnalyticsQueryParams, page: number, pageSize: number) =>
    ['orchestration', 'analytics', 'runs', p.appId, p.scope, p.from ?? null, p.to ?? null, page, pageSize] as const,
  runDetail: (runId: string, p: AnalyticsQueryParams, page: number, pageSize: number) =>
    ['orchestration', 'analytics', 'run', runId, p.scope, page, pageSize] as const,
  signals: (appId: string, scope: AnalyticsQueryParams['scope']) =>
    ['orchestration', 'analytics', 'signals', appId, scope] as const,
};

export function useOrchestrationOverview(params: AnalyticsQueryParams) {
  const enabled = Boolean(params.appId);
  return useQuery<OrchestrationOverview>({
    queryKey: analyticsQueryKeys.overview(params),
    queryFn: () => fetchOverview(params),
    enabled,
    staleTime: STALE_TIME_MS,
  });
}

export function useOrchestrationBreakdown(
  params: AnalyticsQueryParams & { dimension: BreakdownDimension },
) {
  const enabled = Boolean(params.appId);
  return useQuery<OrchestrationBreakdown>({
    queryKey: analyticsQueryKeys.breakdown(params, params.dimension),
    queryFn: () => fetchBreakdown(params),
    enabled,
    staleTime: STALE_TIME_MS,
  });
}

export function useOrchestrationRuns(
  params: AnalyticsQueryParams & { page?: number; pageSize?: number },
) {
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? 20;
  const enabled = Boolean(params.appId);
  return useQuery<OrchestrationRuns>({
    queryKey: analyticsQueryKeys.runs(params, page, pageSize),
    queryFn: () => fetchRuns({ ...params, page, pageSize }),
    enabled,
    staleTime: STALE_TIME_MS,
  });
}

export function useOrchestrationRunDetail(
  runId: string | null | undefined,
  params: AnalyticsQueryParams & { page?: number; pageSize?: number },
) {
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? 50;
  const enabled = Boolean(runId && params.appId);
  return useQuery<OrchestrationRunDetail>({
    queryKey: enabled
      ? analyticsQueryKeys.runDetail(runId as string, params, page, pageSize)
      : (['orchestration', 'analytics', 'run', '__disabled__'] as const),
    queryFn: () => fetchRunDetail(runId as string, { ...params, page, pageSize }),
    enabled,
    staleTime: STALE_TIME_MS,
  });
}

export function useOrchestrationSignals(params: AnalyticsQueryParams) {
  const enabled = Boolean(params.appId);
  return useQuery<OrchestrationSignals>({
    queryKey: analyticsQueryKeys.signals(params.appId, params.scope),
    queryFn: () => fetchSignals({ appId: params.appId, scope: params.scope }),
    enabled,
    staleTime: STALE_TIME_MS,
  });
}
