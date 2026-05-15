/**
 * TanStack hooks for the admin AI settings surface.
 *
 * Located in `services/api/` (not `features/admin/`) so shared `components/ui`
 * surfaces can import without a `ui → features` layering violation. This is a
 * temporary accepted exception for the BYOK plan; revisit when the platform
 * query migration resumes.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  aiSettingsApi,
  type DiscoverModelsResponse,
  type LLMProvider,
  type ProviderConfig,
  type ProviderConfigUpsert,
  type ValidateProviderResponse,
} from '@/services/api/aiSettingsApi';

export const AI_SETTINGS_QUERY_KEY = ['admin', 'ai-settings', 'providers'] as const;

export function useProviderConfigs() {
  return useQuery<ProviderConfig[]>({
    queryKey: AI_SETTINGS_QUERY_KEY,
    queryFn: () => aiSettingsApi.list(),
    staleTime: 30_000,
  });
}

export function useUpsertProvider() {
  const qc = useQueryClient();
  return useMutation<
    ProviderConfig,
    Error,
    { provider: LLMProvider; body: ProviderConfigUpsert }
  >({
    mutationFn: ({ provider, body }) => aiSettingsApi.upsert(provider, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: AI_SETTINGS_QUERY_KEY }),
  });
}

export function useValidateProvider() {
  const qc = useQueryClient();
  return useMutation<ValidateProviderResponse, Error, LLMProvider>({
    mutationFn: (provider) => aiSettingsApi.validate(provider),
    onSuccess: () => qc.invalidateQueries({ queryKey: AI_SETTINGS_QUERY_KEY }),
  });
}

export function useDiscoverModels() {
  return useMutation<
    DiscoverModelsResponse,
    Error,
    { provider: LLMProvider; search: string }
  >({
    mutationFn: ({ provider, search }) => aiSettingsApi.discoverModels(provider, search),
  });
}
