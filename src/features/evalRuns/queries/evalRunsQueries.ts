import { useQuery } from '@tanstack/react-query';
import { fetchEvalRunsPaged } from '@/services/api/evalRunsApi';
import { isActive } from '@/utils/runLifecycle';
import type { PagedEvalRunsParams, PagedEvalRunsResponse } from '@/services/api/evalRunsApi';

const STALE_TIME_MS = 30_000;
const ACTIVE_REFETCH_INTERVAL_MS = 5_000;

export const evalRunsQueryKeys = {
  all: ['evaluation', 'runs'] as const,
  paged: (params: Record<string, unknown>) =>
    ['evaluation', 'runs', 'paged', params] as const,
};

export interface UseEvaluationRunsOptions {
  appId: string;
  page: number;
  pageSize: number;
  sort?: string;
  order?: 'asc' | 'desc';
  runType?: string;
  status?: string;
  q?: string;
  enabled?: boolean;
}

export function useEvaluationRuns(options: UseEvaluationRunsOptions) {
  const {
    appId,
    page,
    pageSize,
    sort,
    order,
    runType,
    status,
    q,
    enabled = true,
  } = options;

  const params: Record<string, unknown> = {
    appId,
    page,
    pageSize,
    sort: sort || undefined,
    order: order || undefined,
    runType: runType || undefined,
    status: status || undefined,
    q: q || undefined,
  };

  return useQuery<PagedEvalRunsResponse>({
    queryKey: evalRunsQueryKeys.paged(params),
    queryFn: () =>
      fetchEvalRunsPaged({
        app_id: appId,
        page,
        page_size: pageSize,
        sort,
        order,
        run_type: runType as PagedEvalRunsParams['run_type'],
        status,
        q,
      }),
    enabled: enabled && Boolean(appId),
    staleTime: STALE_TIME_MS,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data || !data.items) return false;
      return data.items.some((r) => isActive(r.status))
        ? ACTIVE_REFETCH_INTERVAL_MS
        : false;
    },
  });
}
