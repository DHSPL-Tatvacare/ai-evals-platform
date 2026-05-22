/**
 * Workflow-versioning redesign — TanStack Query hooks for the draft/publish
 * lifecycle. The mutation hooks wrap the repointed API client
 * (`saveDraft` → PUT /draft, `publishDraft` → POST /publish) and invalidate
 * the workflow + versions caches so the builder reflects a publish without a
 * manual reload. Mirrors the `queries/runs.ts` pattern.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/services/api/orchestration', () => ({
  getWorkflow: vi.fn(),
  listVersions: vi.fn(),
  saveDraft: vi.fn(),
  publishDraft: vi.fn(),
}));

import {
  getWorkflow,
  listVersions,
  publishDraft,
  saveDraft,
} from '@/services/api/orchestration';
import {
  useWorkflow,
  useWorkflowVersions,
  useSaveDraftMutation,
  usePublishMutation,
  workflowQueryKeys,
} from './workflows';

function wrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children);
}

describe('queries/workflows', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('useWorkflow fetches via getWorkflow when an id is provided', async () => {
    (getWorkflow as ReturnType<typeof vi.fn>).mockResolvedValue({ id: 'wf-1' });
    const { result } = renderHook(() => useWorkflow('wf-1'), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getWorkflow).toHaveBeenCalledWith('wf-1');
    expect(result.current.data).toEqual({ id: 'wf-1' });
  });

  it('useWorkflow is disabled when id is null', () => {
    const { result } = renderHook(() => useWorkflow(null), {
      wrapper: wrapper(),
    });
    expect(result.current.fetchStatus).toBe('idle');
    expect(getWorkflow).not.toHaveBeenCalled();
  });

  it('useWorkflowVersions fetches published history via listVersions', async () => {
    (listVersions as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: 'v2', version: 2 },
    ]);
    const { result } = renderHook(() => useWorkflowVersions('wf-1'), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(listVersions).toHaveBeenCalledWith('wf-1');
  });

  it('useSaveDraftMutation calls saveDraft with the definition', async () => {
    (saveDraft as ReturnType<typeof vi.fn>).mockResolvedValue({ id: 'wf-1' });
    const { result } = renderHook(() => useSaveDraftMutation(), {
      wrapper: wrapper(),
    });
    const def = { nodes: [], edges: [] };
    await act(async () => {
      await result.current.mutateAsync({ workflowId: 'wf-1', definition: def });
    });
    expect(saveDraft).toHaveBeenCalledWith('wf-1', def);
  });

  it('usePublishMutation calls publishDraft with no version id', async () => {
    (publishDraft as ReturnType<typeof vi.fn>).mockResolvedValue({ id: 'v3' });
    const { result } = renderHook(() => usePublishMutation(), {
      wrapper: wrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync({ workflowId: 'wf-1' });
    });
    expect(publishDraft).toHaveBeenCalledWith('wf-1');
  });

  it('query keys are stable and scoped per workflow', () => {
    expect(workflowQueryKeys.workflow('wf-1')).toEqual([
      'orchestration',
      'workflow',
      'wf-1',
    ]);
    expect(workflowQueryKeys.versions('wf-1')).toEqual([
      'orchestration',
      'workflow',
      'wf-1',
      'versions',
    ]);
  });
});
