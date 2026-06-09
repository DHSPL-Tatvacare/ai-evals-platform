import { useQuery } from '@tanstack/react-query';

import { scheduledJobsApi } from '@/services/api/scheduledJobsApi';

import type { ScheduleSourcesResponse } from './types';

/** Launchable sources for a source-bound workload (the workload's `sourceListEndpoint`). Server data → TanStack. */
export function useScheduleSources(endpoint: string | null, appId: string) {
  return useQuery<ScheduleSourcesResponse>({
    queryKey: ['scheduleSources', endpoint, appId],
    queryFn: () => scheduledJobsApi.sources(endpoint as string, appId),
    enabled: Boolean(endpoint),
    staleTime: 30_000,
  });
}
