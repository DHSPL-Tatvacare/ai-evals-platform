import { describe, expect, it, vi, beforeEach } from 'vitest';

const apiRequest = vi.fn();
vi.mock('./client', () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
  ApiError: class ApiError extends Error {},
}));

import {
  createConnection,
  listConnections,
  updateConnection,
} from './orchestrationConnections';
import * as connectionsApi from './orchestrationConnections';

beforeEach(() => {
  apiRequest.mockReset();
  apiRequest.mockResolvedValue([]);
});

describe('orchestrationConnections API layer', () => {
  it('drops the visibility query param from the list URL', async () => {
    // The visibility filter was removed; the list URL must never carry it.
    await listConnections({
      appId: 'inside-sales',
      includeInactive: true,
      // @ts-expect-error visibility is no longer part of ListConnectionsParams
      visibility: 'shared',
    });
    const url = apiRequest.mock.calls[0][0] as string;
    expect(url).toContain('appId=inside-sales');
    expect(url).toContain('includeInactive=true');
    expect(url).not.toContain('visibility');
  });

  it('sends tenantWide + appScopes on create and never visibility', async () => {
    apiRequest.mockResolvedValue({ webhookUrl: null });
    await createConnection({
      appId: 'inside-sales',
      provider: 'bolna',
      name: 'Voice prod',
      config: {},
      tenantWide: true,
      appScopes: ['voice-rx'],
    });
    const body = JSON.parse(
      (apiRequest.mock.calls[0][1] as { body: string }).body,
    );
    expect(body.tenantWide).toBe(true);
    expect(body.appScopes).toEqual(['voice-rx']);
    expect(body).not.toHaveProperty('visibility');
  });

  it('sends tenantWide + appScopes on update and never visibility', async () => {
    apiRequest.mockResolvedValue({ webhookUrl: null });
    await updateConnection('abc', {
      name: 'Voice prod',
      tenantWide: false,
      appScopes: ['voice-rx', 'kaira-bot'],
    });
    const body = JSON.parse(
      (apiRequest.mock.calls[0][1] as { body: string }).body,
    );
    expect(body.tenantWide).toBe(false);
    expect(body.appScopes).toEqual(['voice-rx', 'kaira-bot']);
    expect(body).not.toHaveProperty('visibility');
  });

  it('drops the archiveConnection helper (no DELETE lifecycle)', () => {
    expect(
      (connectionsApi as Record<string, unknown>).archiveConnection,
    ).toBeUndefined();
  });
});
