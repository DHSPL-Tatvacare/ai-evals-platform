import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  discoverCrmObjects,
  getCrmFieldMap,
  getCrmFieldValues,
  getCrmGrains,
  getCrmSyncActivity,
  publishCrmFieldMap,
  triggerCrmSync,
  triggerCrmUnpack,
  type CrmFieldBinding,
  type CrmFieldMap,
  type CrmGrainSchema,
  type CrmSyncRun,
  type DiscoveredObject,
} from '@/services/api/crmSource';

/**
 * TanStack Query hooks for the CRM ingestion surface (Leg 3 Phase 2).
 * Server data only — the in-progress mapping draft is client-only and lives in
 * `crmMappingDraftStore`. CRM-specific reads are namespaced under `['crmSource', …]`;
 * the connections list itself stays on the shared `['integrations','connections']`
 * key owned by `../queries`. Mutations invalidate the NARROWEST relevant key.
 */
export const crmSourceKeys = {
  all: ['crmSource'] as const,
  grains: () => [...crmSourceKeys.all, 'grains'] as const,
  objects: (connectionId: string) => [...crmSourceKeys.all, 'objects', connectionId] as const,
  mapping: (connectionId: string, recordType: string) =>
    [...crmSourceKeys.all, 'mapping', connectionId, recordType] as const,
  sync: (connectionId: string) => [...crmSourceKeys.all, 'sync', connectionId] as const,
  fieldValues: (connectionId: string, recordType: string, field: string) =>
    [...crmSourceKeys.all, 'fieldValues', connectionId, recordType, field] as const,
};

export function useCrmGrains() {
  return useQuery<{ grains: CrmGrainSchema[] }>({
    queryKey: crmSourceKeys.grains(),
    queryFn: getCrmGrains,
    staleTime: 5 * 60_000, // grain schema is static product shape
  });
}

export function useCrmDiscoveredObjects(connectionId: string, enabled: boolean) {
  return useQuery<{ objects: DiscoveredObject[] }>({
    queryKey: crmSourceKeys.objects(connectionId),
    queryFn: () => discoverCrmObjects(connectionId),
    enabled: Boolean(connectionId) && enabled,
    staleTime: 60_000,
    retry: false, // a discovery failure is a creds/provider issue — surface it, don't hammer
  });
}

export function useCrmFieldMap(connectionId: string, recordType: string | null) {
  return useQuery<CrmFieldMap>({
    queryKey: crmSourceKeys.mapping(connectionId, recordType ?? ''),
    queryFn: () => getCrmFieldMap(connectionId, recordType!),
    enabled: Boolean(connectionId && recordType),
    staleTime: 30_000,
  });
}

export function useCrmFieldValues(
  connectionId: string,
  recordType: string | null,
  field: string | null,
) {
  return useQuery<{ field: string; values: string[] }>({
    queryKey: crmSourceKeys.fieldValues(connectionId, recordType ?? '', field ?? ''),
    queryFn: () => getCrmFieldValues(connectionId, recordType!, field!),
    enabled: Boolean(connectionId && recordType && field),
    staleTime: 60_000,
  });
}

export function useCrmSyncActivity(connectionId: string, live: boolean) {
  return useQuery<{ runs: CrmSyncRun[] }>({
    queryKey: crmSourceKeys.sync(connectionId),
    queryFn: () => getCrmSyncActivity(connectionId),
    enabled: Boolean(connectionId),
    refetchInterval: live ? 5_000 : false,
    staleTime: 5_000,
  });
}

export function usePublishCrmFieldMap(connectionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { recordType: string; bindings: CrmFieldBinding[] }) =>
      publishCrmFieldMap(connectionId, body),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: crmSourceKeys.mapping(connectionId, result.recordType) });
      queryClient.invalidateQueries({ queryKey: crmSourceKeys.sync(connectionId) });
    },
  });
}

export function useTriggerCrmSync(connectionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sourceObjects?: string[]) => triggerCrmSync(connectionId, sourceObjects),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: crmSourceKeys.sync(connectionId) });
    },
  });
}

export function useTriggerCrmUnpack(connectionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => triggerCrmUnpack(connectionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: crmSourceKeys.sync(connectionId) });
    },
  });
}
