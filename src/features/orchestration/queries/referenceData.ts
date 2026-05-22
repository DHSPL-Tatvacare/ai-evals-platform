import { useQuery, useQueryClient } from '@tanstack/react-query';

import {
  listConnectionAgents,
  listConnectionTemplates,
  type ProviderAgentsListResponse,
  type ProviderTemplatesListResponse,
} from '@/services/api/orchestrationConnections';

/**
 * Orchestration reference-data hooks.
 *
 * Key shape: `['orchestration', 'connection', connectionId, <resource>]`.
 * Provider template / agent lists rarely change and each fetch is a live
 * vendor roundtrip, while the inspector unmounts on close (keyed motion.div).
 * A long `staleTime` keeps reopening the inspector instant from cache, and a
 * long `gcTime` survives the unmount so the cache isn't evicted between opens.
 *
 * Refresh: the picker's Refresh button calls `refresh()` to bypass both the FE
 * cache and the backend in-process cache for the "I just approved a template"
 * case. `queryClient.fetchQuery` is used rather than `refetch()` so the
 * `{refresh: true}` arg flows through.
 */

const STALE_TIME_MS = 10 * 60_000;
const GC_TIME_MS = 30 * 60_000;

function watiTemplatesKey(connectionId: string) {
  return ['orchestration', 'connection', connectionId, 'wati-templates'] as const;
}

function bolnaAgentsKey(connectionId: string) {
  return ['orchestration', 'connection', connectionId, 'bolna-agents'] as const;
}

function watiTemplatesQueryOptions(
  connectionId: string,
  params?: { refresh?: boolean },
  staleTime = STALE_TIME_MS,
) {
  return {
    queryKey: watiTemplatesKey(connectionId),
    queryFn: params
      ? () => listConnectionTemplates(connectionId, params)
      : () => listConnectionTemplates(connectionId),
    staleTime,
  };
}

function bolnaAgentsQueryOptions(
  connectionId: string,
  params?: { refresh?: boolean },
  staleTime = STALE_TIME_MS,
) {
  return {
    queryKey: bolnaAgentsKey(connectionId),
    queryFn: params
      ? () => listConnectionAgents(connectionId, params)
      : () => listConnectionAgents(connectionId),
    staleTime,
  };
}

export function useWatiTemplates(connectionId: string | null | undefined) {
  const queryClient = useQueryClient();
  const enabled = Boolean(connectionId);

  const query = useQuery<ProviderTemplatesListResponse>({
    queryKey: enabled
      ? watiTemplatesKey(connectionId as string)
      : ['orchestration', 'connection', '__disabled__', 'wati-templates'],
    queryFn: watiTemplatesQueryOptions(connectionId as string).queryFn,
    enabled,
    staleTime: STALE_TIME_MS,
    gcTime: GC_TIME_MS,
  });

  /** Force a network roundtrip past the backend's 30 s cache. Used by the
   *  picker's Refresh button — needed for the rare "I just approved a
   *  template in WATI" case. We bypass `query.refetch()` because that
   *  re-runs the original queryFn (which doesn't carry `refresh: true`).
   *  `fetchQuery` keeps the refresh on the same cache key so both success
   *  and failure propagate through the observed query state. */
  const refresh = async () => {
    if (!connectionId) return query.data ?? null;
    try {
      return await queryClient.fetchQuery(
        watiTemplatesQueryOptions(connectionId, { refresh: true }, 0),
      );
    } catch {
      return queryClient.getQueryData<ProviderTemplatesListResponse>(
        watiTemplatesKey(connectionId),
      ) ?? null;
    }
  };

  return { ...query, refresh };
}

export function useBolnaAgents(connectionId: string | null | undefined) {
  const queryClient = useQueryClient();
  const enabled = Boolean(connectionId);

  const query = useQuery<ProviderAgentsListResponse>({
    queryKey: enabled
      ? bolnaAgentsKey(connectionId as string)
      : ['orchestration', 'connection', '__disabled__', 'bolna-agents'],
    queryFn: bolnaAgentsQueryOptions(connectionId as string).queryFn,
    enabled,
    staleTime: STALE_TIME_MS,
    gcTime: GC_TIME_MS,
  });

  const refresh = async () => {
    if (!connectionId) return query.data ?? null;
    try {
      return await queryClient.fetchQuery(
        bolnaAgentsQueryOptions(connectionId, { refresh: true }, 0),
      );
    } catch {
      return queryClient.getQueryData<ProviderAgentsListResponse>(
        bolnaAgentsKey(connectionId),
      ) ?? null;
    }
  };

  return { ...query, refresh };
}
