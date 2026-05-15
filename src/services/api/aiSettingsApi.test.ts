import { beforeEach, expect, test, vi } from 'vitest';

const { apiRequestMock } = vi.hoisted(() => ({
  apiRequestMock: vi.fn(),
}));

vi.mock('./client', () => ({
  apiRequest: apiRequestMock,
}));

import { aiSettingsApi } from './aiSettingsApi';

beforeEach(() => {
  apiRequestMock.mockReset();
});

test('list hits the providers index', async () => {
  apiRequestMock.mockResolvedValue([]);
  await aiSettingsApi.list();
  expect(apiRequestMock).toHaveBeenCalledWith('/api/admin/ai-settings/providers');
});

test('upsert PUTs JSON-stringified body to the provider path', async () => {
  apiRequestMock.mockResolvedValue({});
  await aiSettingsApi.upsert('openai', {
    isEnabled: true,
    apiKey: 'sk-x',
    baseUrl: null,
    extraConfig: {},
    curatedModels: ['gpt-5.4'],
  });
  expect(apiRequestMock).toHaveBeenCalledTimes(1);
  const [path, init] = apiRequestMock.mock.calls[0];
  expect(path).toBe('/api/admin/ai-settings/providers/openai');
  expect(init?.method).toBe('PUT');
  expect(typeof init?.body).toBe('string');
  expect(JSON.parse(init?.body as string)).toEqual({
    isEnabled: true,
    apiKey: 'sk-x',
    baseUrl: null,
    extraConfig: {},
    curatedModels: ['gpt-5.4'],
  });
});

test('discoverModels POSTs a JSON-stringified search body', async () => {
  apiRequestMock.mockResolvedValue({ models: [] });
  await aiSettingsApi.discoverModels('anthropic', 'haiku');
  const [path, init] = apiRequestMock.mock.calls[0];
  expect(path).toBe('/api/admin/ai-settings/providers/anthropic/discover-models');
  expect(init?.method).toBe('POST');
  expect(JSON.parse(init?.body as string)).toEqual({ search: 'haiku' });
});

test('validate POSTs without a body', async () => {
  apiRequestMock.mockResolvedValue({ validationStatus: 'ok', detail: null });
  await aiSettingsApi.validate('gemini');
  const [path, init] = apiRequestMock.mock.calls[0];
  expect(path).toBe('/api/admin/ai-settings/providers/gemini/validate');
  expect(init?.method).toBe('POST');
  expect(init?.body).toBeUndefined();
});
