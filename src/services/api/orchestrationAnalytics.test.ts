import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./client', () => ({ apiRequest: vi.fn().mockResolvedValue({}) }));

import { apiRequest } from './client';
import {
  fetchBreakdown,
  fetchOverview,
  fetchRunDetail,
  fetchRuns,
  fetchSignals,
} from './orchestrationAnalytics';

const mockRequest = apiRequest as ReturnType<typeof vi.fn>;
const PARAMS = { appId: 'inside-sales', scope: 'mine' as const, from: '2026-05-01', to: '2026-05-29' };

function lastPath(): string {
  return mockRequest.mock.calls[mockRequest.mock.calls.length - 1][0] as string;
}

describe('orchestrationAnalytics service URL building', () => {
  beforeEach(() => mockRequest.mockClear());

  it('fetchOverview builds the query string with appId/scope/from/to', async () => {
    await fetchOverview(PARAMS);
    const path = lastPath();
    expect(path).toContain('/api/orchestration/analytics/overview?');
    expect(path).toContain('appId=inside-sales');
    expect(path).toContain('scope=mine');
    expect(path).toContain('from=2026-05-01');
    expect(path).toContain('to=2026-05-29');
  });

  it('fetchBreakdown includes the dimension param', async () => {
    await fetchBreakdown({ ...PARAMS, dimension: 'connection' });
    const path = lastPath();
    expect(path).toContain('/api/orchestration/analytics/breakdown?');
    expect(path).toContain('dimension=connection');
  });

  it('fetchRuns includes pagination', async () => {
    await fetchRuns({ ...PARAMS, page: 2, pageSize: 25 });
    const path = lastPath();
    expect(path).toContain('/api/orchestration/analytics/runs?');
    expect(path).toContain('page=2');
    expect(path).toContain('pageSize=25');
  });

  it('fetchRunDetail encodes the run id and omits range params', async () => {
    await fetchRunDetail('run 1', PARAMS);
    const path = lastPath();
    expect(path).toContain('/api/orchestration/analytics/runs/run%201?');
    expect(path).toContain('scope=mine');
    expect(path).not.toContain('from=');
  });

  it('fetchSignals only sends appId + scope', async () => {
    await fetchSignals({ appId: 'inside-sales', scope: 'tenant' });
    const path = lastPath();
    expect(path).toContain('/api/orchestration/analytics/signals?');
    expect(path).toContain('scope=tenant');
    expect(path).not.toContain('from=');
  });
});
