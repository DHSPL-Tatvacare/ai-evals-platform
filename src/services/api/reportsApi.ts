import { apiRequest, apiDownload } from './client';
import type { CrossRunAnalyticsResponse } from '@/types/crossRunAnalytics';
import type { PlatformCrossRunNarrative, PlatformCrossRunPayload, PlatformRunReportPayload } from '@/types/platformReports';

export const reportsApi = {
  /**
   * Fetch the full report for a completed eval run.
   * Cached after first generation; pass refresh=true to force regeneration.
   * Optionally specify provider/model for AI narrative generation.
   */
  fetchReport: <TReport = PlatformRunReportPayload>(runId: string, opts?: { refresh?: boolean; cacheOnly?: boolean; provider?: string; model?: string }): Promise<TReport> => {
    const params = new URLSearchParams();
    if (opts?.refresh) params.set('refresh', 'true');
    if (opts?.cacheOnly) params.set('cache_only', 'true');
    if (opts?.provider) params.set('provider', opts.provider);
    if (opts?.model) params.set('model', opts.model);
    const qs = params.toString();
    return apiRequest<TReport>(
      `/api/reports/${runId}${qs ? `?${qs}` : ''}`,
    );
  },

  /** Export report as PDF via server-side headless browser rendering. */
  exportPdf: (runId: string): Promise<Blob> =>
    apiDownload(`/api/reports/${runId}/export-pdf`),

  /** Fetch cached cross-run analytics for an app. */
  fetchCrossRunAnalytics: <TAnalytics = PlatformCrossRunPayload>(appId: string): Promise<CrossRunAnalyticsResponse<TAnalytics>> => {
    const params = new URLSearchParams({ app_id: appId });
    return apiRequest<CrossRunAnalyticsResponse<TAnalytics>>(`/api/reports/cross-run-analytics?${params}`);
  },

  /** Recompute cross-run analytics from single_run caches and persist. */
  refreshCrossRunAnalytics: <TAnalytics = PlatformCrossRunPayload>(appId: string, limit?: number): Promise<CrossRunAnalyticsResponse<TAnalytics>> => {
    const params = new URLSearchParams({ app_id: appId });
    if (limit) params.set('limit', String(limit));
    return apiRequest<CrossRunAnalyticsResponse<TAnalytics>>(`/api/reports/cross-run-analytics/refresh?${params}`, {
      method: 'POST',
    });
  },

  /** Generate AI summary of cross-run analytics. */
  generateCrossRunSummary: (payload: { appId: string; provider?: string; model?: string }): Promise<PlatformCrossRunNarrative> =>
    apiRequest<PlatformCrossRunNarrative>('/api/reports/cross-run-ai-summary', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};
