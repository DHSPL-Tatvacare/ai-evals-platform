import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  activateCrmDataset,
  discoverCrmObjects,
  getCrmDatasetFieldValues,
  getCrmDatasetPreview,
  getCrmFieldMap,
  getCrmFieldValues,
  getCrmFilterCapabilities,
  getCrmGrains,
  getCrmRawSample,
  getCrmResolvedPreview,
  getCrmSyncActivity,
  getCrmUnpackedSample,
  listCrmDatasets,
  publishCrmFieldMap,
  saveCrmDatasetDraft,
  triggerCrmSync,
  triggerCrmUnpack,
  type CrmDatasetActivateResult,
  type CrmDatasetDraftBody,
  type CrmDatasetDraftResult,
  type CrmDatasetSummary,
  type CrmFieldBinding,
  type CrmFieldMap,
  type CrmFilterCapabilities,
  type CrmGrainSchema,
  type CrmRawSample,
  type CrmResolvedPreview,
  type CrmSyncRun,
  type CrmUnpackedSample,
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
  preview: (connectionId: string, recordType: string) =>
    [...crmSourceKeys.all, 'preview', connectionId, recordType] as const,
  datasets: (connectionId: string) => [...crmSourceKeys.all, 'datasets', connectionId] as const,
  rawSample: (connectionId: string, recordType: string) =>
    [...crmSourceKeys.all, 'rawSample', connectionId, recordType] as const,
  filterCapabilities: (connectionId: string, recordType: string) =>
    [...crmSourceKeys.all, 'filterCapabilities', connectionId, recordType] as const,
  datasetFieldValues: (connectionId: string, recordType: string, field: string) =>
    [...crmSourceKeys.all, 'datasetFieldValues', connectionId, recordType, field] as const,
  datasetPreview: (connectionId: string, recordType: string) =>
    [...crmSourceKeys.all, 'datasetPreview', connectionId, recordType] as const,
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

export function useCrmResolvedPreview(connectionId: string, recordType: string | null) {
  return useQuery<CrmResolvedPreview>({
    queryKey: crmSourceKeys.preview(connectionId, recordType ?? ''),
    queryFn: () => getCrmResolvedPreview(connectionId, recordType!),
    enabled: Boolean(connectionId && recordType),
    staleTime: 30_000,
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
      queryClient.invalidateQueries({ queryKey: crmSourceKeys.preview(connectionId, result.recordType) });
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
      queryClient.invalidateQueries({ queryKey: [...crmSourceKeys.all, 'preview', connectionId] });
    },
  });
}

export function useConnectionDatasets(connectionId: string) {
  return useQuery<{ datasets: CrmDatasetSummary[] }>({
    queryKey: crmSourceKeys.datasets(connectionId),
    queryFn: () => listCrmDatasets(connectionId),
    enabled: Boolean(connectionId),
    staleTime: 30_000,
    retry: false, // a discovery failure is a creds/provider issue — surface it, don't hammer
  });
}

export function useRawSample(connectionId: string, recordType: string | null) {
  return useQuery<CrmRawSample>({
    queryKey: crmSourceKeys.rawSample(connectionId, recordType ?? ''),
    queryFn: () => getCrmRawSample(connectionId, recordType!),
    enabled: Boolean(connectionId && recordType),
    staleTime: 60_000,
    retry: false,
  });
}

export function useUnpackedSample(connectionId: string) {
  return useMutation<CrmUnpackedSample, Error, CrmDatasetDraftBody>({
    mutationFn: (body) => getCrmUnpackedSample(connectionId, body),
  });
}

export function useFilterCapabilities(connectionId: string, recordType: string | null) {
  return useQuery<CrmFilterCapabilities>({
    queryKey: crmSourceKeys.filterCapabilities(connectionId, recordType ?? ''),
    queryFn: () => getCrmFilterCapabilities(connectionId, recordType!),
    enabled: Boolean(connectionId && recordType),
    staleTime: 60_000,
    retry: false,
  });
}

export function useFieldValues(
  connectionId: string,
  recordType: string | null,
  field: string | null,
) {
  return useQuery<{ field: string; values: string[] }>({
    queryKey: crmSourceKeys.datasetFieldValues(connectionId, recordType ?? '', field ?? ''),
    queryFn: () => getCrmDatasetFieldValues(connectionId, recordType!, field!),
    enabled: Boolean(connectionId && recordType && field),
    staleTime: 60_000,
    retry: false,
  });
}

export function useDatasetPreview(connectionId: string, recordType: string | null) {
  return useQuery<CrmResolvedPreview>({
    queryKey: crmSourceKeys.datasetPreview(connectionId, recordType ?? ''),
    queryFn: () => getCrmDatasetPreview(connectionId, recordType!),
    enabled: Boolean(connectionId && recordType),
    staleTime: 30_000,
  });
}

export function useSaveDraft(connectionId: string) {
  const queryClient = useQueryClient();
  return useMutation<CrmDatasetDraftResult, Error, CrmDatasetDraftBody>({
    mutationFn: (body) => saveCrmDatasetDraft(connectionId, body),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: crmSourceKeys.datasets(connectionId) });
      queryClient.invalidateQueries({ queryKey: crmSourceKeys.mapping(connectionId, result.recordType) });
    },
  });
}

export function useActivateDataset(connectionId: string) {
  const queryClient = useQueryClient();
  return useMutation<CrmDatasetActivateResult, Error, string>({
    mutationFn: (recordType) => activateCrmDataset(connectionId, recordType),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: crmSourceKeys.datasets(connectionId) });
      queryClient.invalidateQueries({ queryKey: crmSourceKeys.mapping(connectionId, result.recordType) });
      queryClient.invalidateQueries({ queryKey: crmSourceKeys.datasetPreview(connectionId, result.recordType) });
    },
  });
}
