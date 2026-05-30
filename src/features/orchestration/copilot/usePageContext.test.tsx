/**
 * Page-context detector tests.
 *
 * Cases:
 *   1. Route doesn't match builder → 'none'
 *   2. Route matches + edit mode → full snapshot
 *   3. Route matches + view mode → snapshot with viewMode='view'
 *   4. The `canvasContextEnabled` toggle gates the non-hook snapshot: when
 *      off, `getPageContextSnapshot` returns 'none' so the supervisor never
 *      reads the canvas.
 */
import { renderHook, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import { getPageContextSnapshot, usePageContext } from './usePageContext';

function wrap(initialEntries: string[]) {
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
  );
  return Wrapper;
}

function seedStore({ viewMode }: { viewMode: 'view' | 'edit' }) {
  const store = useWorkflowBuilderStore.getState();
  store.reset();
  store.setMetadata({
    workflowId: 'wf_demo',
    versionId: 'v_1',
    name: 'Demo concierge',
    workflowType: 'crm',
  });
  store.setViewMode(viewMode);
}

describe('usePageContext', () => {
  beforeEach(() => {
    useWorkflowBuilderStore.getState().reset();
  });

  it("returns 'none' when the route doesn't match a builder", () => {
    seedStore({ viewMode: 'edit' });
    const { result } = renderHook(() => usePageContext(), {
      wrapper: wrap(['/inside-sales/runs']),
    });
    expect(result.current.kind).toBe('none');
  });

  it('returns the full snapshot when on the builder + edit', () => {
    seedStore({ viewMode: 'edit' });
    const { result } = renderHook(() => usePageContext(), {
      wrapper: wrap(['/inside-sales/orchestration/workflows/wf_demo']),
    });
    expect(result.current.kind).toBe('orchestration_builder');
    if (result.current.kind !== 'orchestration_builder') return;
    expect(result.current.appId).toBe('inside-sales');
    expect(result.current.workflowId).toBe('wf_demo');
    expect(result.current.versionId).toBe('v_1');
    expect(result.current.workflowType).toBe('crm');
    expect(result.current.workflowName).toBe('Demo concierge');
    expect(result.current.viewMode).toBe('edit');
    expect(result.current.dataHash).toEqual(expect.any(String));
    expect(result.current.definition.nodes).toEqual([]);
  });

  it("carries viewMode='view' when the route matches but the user is viewing", () => {
    seedStore({ viewMode: 'view' });
    const { result } = renderHook(() => usePageContext(), {
      wrapper: wrap(['/inside-sales/orchestration/workflows/wf_demo']),
    });
    expect(result.current.kind).toBe('orchestration_builder');
    if (result.current.kind !== 'orchestration_builder') return;
    expect(result.current.viewMode).toBe('view');
  });

  it("returns 'none' when on the builder but workflowId not yet hydrated", () => {
    useWorkflowBuilderStore.getState().reset();
    const { result } = renderHook(() => usePageContext(), {
      wrapper: wrap(['/inside-sales/orchestration/workflows/wf_pending']),
    });
    expect(result.current.kind).toBe('none');
  });

  it('updates when viewMode flips after mount', () => {
    seedStore({ viewMode: 'view' });
    const { result } = renderHook(() => usePageContext(), {
      wrapper: wrap(['/inside-sales/orchestration/workflows/wf_demo']),
    });
    if (result.current.kind !== 'orchestration_builder') {
      throw new Error('expected builder context');
    }
    expect(result.current.viewMode).toBe('view');

    act(() => {
      useWorkflowBuilderStore.getState().setViewMode('edit');
    });

    if (result.current.kind !== 'orchestration_builder') {
      throw new Error('expected builder context post-flip');
    }
    expect(result.current.viewMode).toBe('edit');
  });
});

describe('getPageContextSnapshot', () => {
  beforeEach(() => {
    useWorkflowBuilderStore.getState().reset();
    window.history.replaceState({}, '', '/');
  });

  it('reads workflow store + window pathname without React', () => {
    seedStore({ viewMode: 'edit' });
    window.history.replaceState({}, '', '/inside-sales/orchestration/workflows/wf_demo');
    const ctx = getPageContextSnapshot();
    expect(ctx.kind).toBe('orchestration_builder');
  });

  it("returns 'none' when off the builder", () => {
    seedStore({ viewMode: 'edit' });
    window.history.replaceState({}, '', '/inside-sales/runs');
    expect(getPageContextSnapshot().kind).toBe('none');
  });

  it("returns 'none' when the canvas context toggle is off", () => {
    seedStore({ viewMode: 'edit' });
    useWorkflowBuilderStore.getState().setCanvasContextEnabled(false);
    window.history.replaceState({}, '', '/inside-sales/orchestration/workflows/wf_demo');
    expect(getPageContextSnapshot().kind).toBe('none');
  });

  it('returns context again once the toggle is flipped back on', () => {
    seedStore({ viewMode: 'edit' });
    window.history.replaceState({}, '', '/inside-sales/orchestration/workflows/wf_demo');
    useWorkflowBuilderStore.getState().setCanvasContextEnabled(false);
    expect(getPageContextSnapshot().kind).toBe('none');
    useWorkflowBuilderStore.getState().setCanvasContextEnabled(true);
    expect(getPageContextSnapshot().kind).toBe('orchestration_builder');
  });
});
