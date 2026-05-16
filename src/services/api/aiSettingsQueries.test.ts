/**
 * Hook tests for the admin AI settings TanStack hooks.
 *
 * Mounted with a mocked `apiRequest` so the test asserts:
 *   - `useProviderConfigs` uses the canonical query key + calls GET on
 *     `/api/admin/ai-settings/providers` and returns the typed list.
 *   - `useUpsertProvider` sends a PUT with a JSON-stringified body and
 *     invalidates the providers query key on success.
 *   - `useValidateProvider` POSTs to `/validate` and invalidates the same key.
 *   - `useDiscoverModels` POSTs `{search}` and does NOT invalidate the
 *     providers query (no cache write — it's a transient search).
 *
 * Pattern is intentionally narrow: this is the network/cache contract test
 * the plan called for. Component-level Combobox + curation behaviour is
 * exercised in the `ProviderConfigPanel` integration path.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';

vi.mock('@/services/api/client', () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from '@/services/api/client';
import {
  AI_SETTINGS_QUERY_KEY,
  useDiscoverModels,
  useProviderConfigs,
  useUpsertProvider,
  useValidateProvider,
} from './aiSettingsQueries';

const mockedApiRequest = apiRequest as unknown as ReturnType<typeof vi.fn>;

function makeWrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client }, children);
  };
}

function freshClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

const PROVIDER_FIXTURE = {
  provider: 'openai',
  isEnabled: true,
  hasApiKey: true,
  apiKeyPreview: 'sk-p••••XYZ1',
  baseUrl: null,
  extraConfig: {},
  curatedModels: ['gpt-5.4'],
  validationStatus: 'ok',
  lastValidatedAt: null,
};

beforeEach(() => {
  mockedApiRequest.mockReset();
});

describe('useProviderConfigs', () => {
  it('GETs /api/admin/ai-settings/providers under the canonical key', async () => {
    mockedApiRequest.mockResolvedValueOnce([PROVIDER_FIXTURE]);
    const client = freshClient();

    const { result } = renderHook(() => useProviderConfigs(), {
      wrapper: makeWrapper(client),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedApiRequest).toHaveBeenCalledWith('/api/admin/ai-settings/providers');
    expect(result.current.data).toEqual([PROVIDER_FIXTURE]);
    expect(AI_SETTINGS_QUERY_KEY).toEqual(['admin', 'ai-settings', 'providers']);
    expect(client.getQueryData(AI_SETTINGS_QUERY_KEY)).toEqual([PROVIDER_FIXTURE]);
  });
});

describe('useUpsertProvider', () => {
  it('PUTs JSON-stringified body and invalidates the providers query', async () => {
    mockedApiRequest.mockResolvedValueOnce(PROVIDER_FIXTURE);
    const client = freshClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useUpsertProvider(), {
      wrapper: makeWrapper(client),
    });

    await result.current.mutateAsync({
      provider: 'openai',
      body: {
        isEnabled: true,
        apiKey: 'sk-new',
        baseUrl: null,
        extraConfig: {},
        curatedModels: ['gpt-5.4'],
      },
    });

    expect(mockedApiRequest).toHaveBeenCalledTimes(1);
    const [path, options] = mockedApiRequest.mock.calls[0];
    expect(path).toBe('/api/admin/ai-settings/providers/openai');
    expect(options.method).toBe('PUT');
    // Body must be a JSON string per CLAUDE.md / Phase-2 invariant.
    expect(typeof options.body).toBe('string');
    expect(JSON.parse(options.body)).toEqual({
      isEnabled: true,
      apiKey: 'sk-new',
      baseUrl: null,
      extraConfig: {},
      curatedModels: ['gpt-5.4'],
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: AI_SETTINGS_QUERY_KEY });
  });
});

describe('useValidateProvider', () => {
  it('POSTs to /validate and invalidates the providers query on success', async () => {
    mockedApiRequest.mockResolvedValueOnce({ validationStatus: 'ok', detail: null });
    const client = freshClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useValidateProvider(), {
      wrapper: makeWrapper(client),
    });

    const out = await result.current.mutateAsync('anthropic');

    expect(out).toEqual({ validationStatus: 'ok', detail: null });
    const [path, options] = mockedApiRequest.mock.calls[0];
    expect(path).toBe('/api/admin/ai-settings/providers/anthropic/validate');
    expect(options.method).toBe('POST');
    expect(invalidate).toHaveBeenCalledWith({ queryKey: AI_SETTINGS_QUERY_KEY });
  });
});

describe('useDiscoverModels', () => {
  it('POSTs {search} and does NOT invalidate the providers cache', async () => {
    mockedApiRequest.mockResolvedValueOnce({ models: ['gpt-5.4', 'gpt-5.4-mini'] });
    const client = freshClient();
    const invalidate = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useDiscoverModels(), {
      wrapper: makeWrapper(client),
    });

    const out = await result.current.mutateAsync({
      provider: 'openai',
      search: 'gpt',
    });

    expect(out.models).toEqual(['gpt-5.4', 'gpt-5.4-mini']);
    const [path, options] = mockedApiRequest.mock.calls[0];
    expect(path).toBe('/api/admin/ai-settings/providers/openai/discover-models');
    expect(options.method).toBe('POST');
    expect(JSON.parse(options.body)).toEqual({ search: 'gpt' });
    // Discovery is transient; no cache write.
    expect(invalidate).not.toHaveBeenCalled();
  });
});
