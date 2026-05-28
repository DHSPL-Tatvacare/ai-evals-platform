import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/services/api/orchestrationAnalytics', () => ({
  fetchOverview: vi.fn(),
  fetchBreakdown: vi.fn(),
  fetchRuns: vi.fn(),
  fetchRunDetail: vi.fn(),
  fetchSignals: vi.fn(),
}));

import {
  fetchBreakdown,
  fetchOverview,
  fetchRunDetail,
  fetchRuns,
  fetchSignals,
} from '@/services/api/orchestrationAnalytics';
import {
  useOrchestrationBreakdown,
  useOrchestrationOverview,
  useOrchestrationRunDetail,
  useOrchestrationRuns,
  useOrchestrationSignals,
} from './queries';

function wrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children);
}

const PARAMS = { appId: 'inside-sales', scope: 'mine' as const, from: '2026-05-01', to: '2026-05-29' };

describe('orchestration analytics queries', () => {
  beforeEach(() => vi.clearAllMocks());

  it('useOrchestrationOverview calls fetchOverview with the params', async () => {
    (fetchOverview as ReturnType<typeof vi.fn>).mockResolvedValue({ campaigns: 2 });
    const { result } = renderHook(() => useOrchestrationOverview(PARAMS), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchOverview).toHaveBeenCalledWith(PARAMS);
  });

  it('useOrchestrationOverview is disabled without an appId', () => {
    const { result } = renderHook(
      () => useOrchestrationOverview({ ...PARAMS, appId: '' }),
      { wrapper: wrapper() },
    );
    expect(result.current.fetchStatus).toBe('idle');
    expect(fetchOverview).not.toHaveBeenCalled();
  });

  it('useOrchestrationBreakdown passes the dimension', async () => {
    (fetchBreakdown as ReturnType<typeof vi.fn>).mockResolvedValue({ dimension: 'channel', rows: [] });
    const { result } = renderHook(
      () => useOrchestrationBreakdown({ ...PARAMS, dimension: 'channel' }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchBreakdown).toHaveBeenCalledWith({ ...PARAMS, dimension: 'channel' });
  });

  it('useOrchestrationRuns passes pagination', async () => {
    (fetchRuns as ReturnType<typeof vi.fn>).mockResolvedValue({ rows: [], total: 0, page: 1, pageSize: 20 });
    const { result } = renderHook(
      () => useOrchestrationRuns({ ...PARAMS, page: 2, pageSize: 20 }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchRuns).toHaveBeenCalledWith({ ...PARAMS, page: 2, pageSize: 20 });
  });

  it('useOrchestrationRunDetail is disabled when runId is null', () => {
    const { result } = renderHook(
      () => useOrchestrationRunDetail(null, PARAMS),
      { wrapper: wrapper() },
    );
    expect(result.current.fetchStatus).toBe('idle');
    expect(fetchRunDetail).not.toHaveBeenCalled();
  });

  it('useOrchestrationRunDetail fetches when a runId is given', async () => {
    (fetchRunDetail as ReturnType<typeof vi.fn>).mockResolvedValue({ runId: 'r1' });
    const { result } = renderHook(
      () => useOrchestrationRunDetail('r1', PARAMS),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchRunDetail).toHaveBeenCalledWith('r1', { ...PARAMS, page: 1, pageSize: 50 });
  });

  it('useOrchestrationSignals calls fetchSignals with appId + scope', async () => {
    (fetchSignals as ReturnType<typeof vi.fn>).mockResolvedValue({ signals: [] });
    const { result } = renderHook(() => useOrchestrationSignals(PARAMS), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchSignals).toHaveBeenCalledWith({ appId: PARAMS.appId, scope: PARAMS.scope });
  });
});
