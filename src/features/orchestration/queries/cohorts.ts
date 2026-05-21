/**
 * Saved cohort TanStack Query hooks. Server data via apiQueryFn so the
 * shared 401-refresh-and-retry flow stays in effect.
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { fetchCohortColumnValues, fetchCohortSources } from '@/services/api/orchestration';
import { useDebounce } from '@/hooks/useDebounce';
import type { CohortSource, WorkflowType } from '@/features/orchestration/types';
import type { ComboboxOption } from '@/components/ui/Combobox';
import {
  createCohort,
  createDraftVersion,
  deleteCohort,
  editDraftVersion,
  getCohort,
  listCohorts,
  listUsedBy,
  publishVersion,
  updateCohort,
  type CohortDetailResponse,
  type CohortResponse,
  type CohortVersionPayload,
  type CreateCohortBody,
  type UpdateCohortBody,
  type WorkflowBindingResponse,
} from '@/services/api/orchestrationCohorts';

export const cohortQueryKeys = {
  list: (appId: string) => ['orchestration', 'cohorts', 'list', appId] as const,
  detail: (cohortId: string) =>
    ['orchestration', 'cohorts', 'detail', cohortId] as const,
  usedBy: (cohortId: string) =>
    ['orchestration', 'cohorts', 'used-by', cohortId] as const,
  sources: (workflowType: string, appId: string) =>
    ['orchestration', 'cohort-sources', workflowType, appId] as const,
  columnValues: (sourceRef: string, column: string, q: string) =>
    ['orchestration', 'cohortColumnValues', sourceRef, column, q] as const,
};

export function useCohortSources(
  workflowType: WorkflowType | null | undefined,
  appId: string | null | undefined,
) {
  return useQuery<CohortSource[]>({
    queryKey: cohortQueryKeys.sources(workflowType ?? '', appId ?? ''),
    queryFn: () =>
      fetchCohortSources({
        workflowType: workflowType as WorkflowType,
        appId: appId as string,
      }),
    enabled: Boolean(appId),
  });
}

/** Async column-value typeahead for the datatype-driven filter value picker.
 *  Debounces the search query 250 ms before issuing a network request so the
 *  user can type freely without hammering the endpoint. */
export function useCohortColumnValues(
  sourceRef: string | null | undefined,
  column: string | null | undefined,
  { limit = 50 }: { limit?: number } = {},
): { options: ComboboxOption[]; loading: boolean; onSearchChange: (q: string) => void } {
  const [rawQuery, setRawQuery] = useState('');
  const debouncedQuery = useDebounce(rawQuery, 250);

  const { data, isFetching } = useQuery<{ values: string[]; hasMore: boolean }>({
    queryKey: cohortQueryKeys.columnValues(sourceRef ?? '', column ?? '', debouncedQuery),
    queryFn: () =>
      fetchCohortColumnValues({
        sourceRef: sourceRef as string,
        column: column as string,
        q: debouncedQuery || undefined,
        limit,
      }),
    enabled: Boolean(sourceRef) && Boolean(column),
    staleTime: 30_000,
  });

  const options: ComboboxOption[] = (data?.values ?? []).map((v) => ({ value: v, label: v }));
  return { options, loading: isFetching, onSearchChange: setRawQuery };
}

export function useCohorts(appId: string | null | undefined) {
  return useQuery<CohortResponse[]>({
    queryKey: cohortQueryKeys.list(appId ?? ''),
    queryFn: () => listCohorts({ appId: appId as string }),
    enabled: Boolean(appId),
  });
}

export function useCohort(cohortId: string | null | undefined) {
  return useQuery<CohortDetailResponse>({
    queryKey: cohortQueryKeys.detail(cohortId ?? ''),
    queryFn: () => getCohort(cohortId as string),
    enabled: Boolean(cohortId),
  });
}

export function useCohortUsedBy(cohortId: string | null | undefined) {
  return useQuery<WorkflowBindingResponse[]>({
    queryKey: cohortQueryKeys.usedBy(cohortId ?? ''),
    queryFn: () => listUsedBy(cohortId as string),
    enabled: Boolean(cohortId),
  });
}

export function useCreateCohort() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateCohortBody) => createCohort(body),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: cohortQueryKeys.list(created.appId) });
    },
  });
}

export function useUpdateCohort(cohortId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateCohortBody) => updateCohort(cohortId, body),
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: cohortQueryKeys.list(updated.appId) });
      qc.setQueryData(cohortQueryKeys.detail(cohortId), updated);
    },
  });
}

export function useDeleteCohort() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cohortId: string) => deleteCohort(cohortId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['orchestration', 'cohorts'] });
    },
  });
}

export function useCreateDraftVersion(cohortId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CohortVersionPayload) =>
      createDraftVersion(cohortId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cohortQueryKeys.detail(cohortId) });
    },
  });
}

export function useEditDraftVersion(cohortId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      versionId,
      payload,
    }: {
      versionId: string;
      payload: CohortVersionPayload;
    }) => editDraftVersion(cohortId, versionId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cohortQueryKeys.detail(cohortId) });
    },
  });
}

export function usePublishVersion(cohortId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (versionId: string) => publishVersion(cohortId, versionId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cohortQueryKeys.detail(cohortId) });
      qc.invalidateQueries({ queryKey: ['orchestration', 'cohorts', 'list'] });
    },
  });
}
