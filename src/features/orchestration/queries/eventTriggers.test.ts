import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/services/api/orchestrationTriggers', () => ({
  getEventCatalog: vi.fn(),
  listEventTriggers: vi.fn(),
  createEventTrigger: vi.fn(),
  updateEventTrigger: vi.fn(),
  deleteEventTrigger: vi.fn(),
  rotateEventTriggerToken: vi.fn(),
}));

import {
  getEventCatalog,
  listEventTriggers,
} from '@/services/api/orchestrationTriggers';
import { useEventCatalog, useEventTriggers } from './eventTriggers';

function wrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children);
}

describe('queries/eventTriggers', () => {
  beforeEach(() => vi.clearAllMocks());

  it('passes the lowercase workflow_type through to the catalog endpoint', async () => {
    (getEventCatalog as ReturnType<typeof vi.fn>).mockResolvedValue({
      workflowType: 'clinical',
      events: [],
    });
    const { result } = renderHook(() => useEventCatalog('clinical', 'app-1'), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getEventCatalog).toHaveBeenCalledWith({ workflowType: 'clinical' });
  });

  it('disables the catalog query until both workflow_type and appId are known', () => {
    const { result } = renderHook(() => useEventCatalog(null, 'app-1'), {
      wrapper: wrapper(),
    });
    expect(getEventCatalog).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('lists triggers for a workflow', async () => {
    (listEventTriggers as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: 't-1', webhookTokenMasked: 'ab••••cd' },
    ]);
    const { result } = renderHook(() => useEventTriggers('wf-1'), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(listEventTriggers).toHaveBeenCalledWith('wf-1');
    expect(result.current.data).toHaveLength(1);
  });
});
