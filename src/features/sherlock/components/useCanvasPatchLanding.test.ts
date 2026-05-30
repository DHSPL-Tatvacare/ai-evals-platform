import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { create } from 'zustand';

import type { CanvasPatchPart } from '@/features/sherlock/generated/sherlockContract';
import type { ApplyCanvasPatchResult } from '@/features/orchestration/copilot/canvasPatchApplier';

import { useCanvasPatchLanding } from './useCanvasPatchLanding';

const landCanvasPatch = vi.fn<
  (partId: string, patch: unknown) => Promise<ApplyCanvasPatchResult | undefined>
>();
const applyInverse = vi.fn();
const markChanged = vi.fn();
const applyCanvasPatchSpy = vi.fn<
  (raw: unknown) => Promise<ApplyCanvasPatchResult>
>();

interface MockStoreState {
  landCanvasPatch: typeof landCanvasPatch;
  applyInverse: typeof applyInverse;
  markChanged: typeof markChanged;
  paletteCatalog: unknown[];
  canvasEdits: Record<string, { result: ApplyCanvasPatchResult; changedNodeIds: string[] }>;
}

// A real vanilla zustand store so selector subscriptions notify on mutation —
// exactly like the production store the hook reads from.
const useWorkflowBuilderStore = create<MockStoreState>(() => ({
  landCanvasPatch,
  applyInverse,
  markChanged,
  paletteCatalog: [],
  canvasEdits: {},
}));

function recordEdit(partId: string, result: ApplyCanvasPatchResult, changedNodeIds: string[]) {
  useWorkflowBuilderStore.setState((s) => ({
    canvasEdits: { ...s.canvasEdits, [partId]: { result, changedNodeIds } },
  }));
}

vi.mock('@/features/orchestration/store/workflowBuilderStore', () => ({
  useWorkflowBuilderStore: (selector: (s: MockStoreState) => unknown) =>
    useWorkflowBuilderStore(selector),
}));

vi.mock('@/features/orchestration/copilot/canvasPatchApplier', () => ({
  applyCanvasPatch: (raw: unknown) => applyCanvasPatchSpy(raw),
}));

function makePart(id: string): CanvasPatchPart {
  return {
    chat_session_id: 'sess-1',
    created_at: 0,
    id,
    seq: 1,
    type: 'canvas_patch',
    patch: {
      workflow_id: 'wf-1',
      version_id: null,
      base_data_hash: 'h0',
      rationale: 'because',
      ops: [
        {
          op: 'add_node',
          node_id: 'n1',
          payload: { node_type: 'voice.place_call', config: {} },
        },
      ],
    },
  };
}

const appliedResult: ApplyCanvasPatchResult = {
  kind: 'applied',
  opsApplied: 1,
  addedNodeIds: ['n1'],
  editedNodeIds: [],
  removedNodeIds: [],
  connectEdgeIds: [],
  rationale: 'because',
  inverse: [],
};

beforeEach(() => {
  landCanvasPatch.mockReset();
  applyInverse.mockReset();
  markChanged.mockReset();
  applyCanvasPatchSpy.mockReset();
  useWorkflowBuilderStore.setState({
    landCanvasPatch,
    applyInverse,
    markChanged,
    paletteCatalog: [],
    canvasEdits: {},
  });
  landCanvasPatch.mockImplementation(async (partId) => {
    recordEdit(partId, appliedResult, ['n1']);
    return appliedResult;
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('useCanvasPatchLanding', () => {
  it('lands the patch exactly once on mount and across a re-render', async () => {
    const part = makePart('p1');
    const { rerender } = renderHook(() => useCanvasPatchLanding(part));
    await act(async () => {});
    rerender();
    await act(async () => {});
    expect(landCanvasPatch).toHaveBeenCalledTimes(1);
    expect(landCanvasPatch).toHaveBeenCalledWith('p1', part.patch);
  });

  it('maps an applied result to the applied variant with summary + chips', async () => {
    const { result } = renderHook(() => useCanvasPatchLanding(makePart('p2')));
    await act(async () => {});
    expect(result.current.view).toBe('card');
    expect(result.current.variant).toBe('applied');
    expect(result.current.summary).toMatch(/Added/i);
    expect(result.current.chips.length).toBeGreaterThan(0);
  });

  // Non-applied kinds: the production store returns the result but records NO
  // canvasEdits entry. The bridge must derive the variant from landCanvasPatch's
  // RETURN value, not from canvasEdits[part.id] (which stays undefined here).
  it('maps hash_mismatch to the conflict variant from the returned result', async () => {
    landCanvasPatch.mockResolvedValue({ kind: 'hash_mismatch', rationale: 'drift' });
    const { result } = renderHook(() => useCanvasPatchLanding(makePart('p3')));
    await act(async () => {});
    expect(result.current.variant).toBe('conflict');
  });

  it('maps version_mismatch to the blocked variant from the returned result', async () => {
    landCanvasPatch.mockResolvedValue({ kind: 'version_mismatch' });
    const { result } = renderHook(() => useCanvasPatchLanding(makePart('p4')));
    await act(async () => {});
    expect(result.current.variant).toBe('blocked');
  });

  it('surfaces config_invalid nodeName from the returned result', async () => {
    landCanvasPatch.mockResolvedValue({
      kind: 'config_invalid',
      nodeId: 'n-bad',
      opKind: 'add_node',
    });
    const { result } = renderHook(() => useCanvasPatchLanding(makePart('p4b')));
    await act(async () => {});
    expect(result.current.variant).toBe('blocked');
    expect(result.current.nodeName).toBe('n-bad');
  });

  it('surfaces an aborted result as a stopped note from the returned result', async () => {
    landCanvasPatch.mockResolvedValue({ kind: 'aborted', opsApplied: 1 });
    const { result } = renderHook(() => useCanvasPatchLanding(makePart('p5')));
    await act(async () => {});
    expect(result.current.view).toBe('stopped');
    expect(result.current.stoppedNote).toMatch(/Stopped/i);
  });

  it('onUndo replays the inverse and flips to the reverted view', async () => {
    const { result } = renderHook(() => useCanvasPatchLanding(makePart('p6')));
    await act(async () => {});
    act(() => result.current.onUndo());
    expect(applyInverse).toHaveBeenCalledWith('p6');
    expect(result.current.variant).toBe('reverted');
  });

  it('onShowOnCanvas re-flashes the changed nodes', async () => {
    const { result } = renderHook(() => useCanvasPatchLanding(makePart('p7')));
    await act(async () => {});
    act(() => result.current.onShowOnCanvas());
    expect(markChanged).toHaveBeenCalledWith(['n1']);
  });

  it('onKeepAsIs hides the card', async () => {
    const { result } = renderHook(() => useCanvasPatchLanding(makePart('p8')));
    await act(async () => {});
    act(() => result.current.onKeepAsIs());
    expect(result.current.view).toBe('hidden');
  });
});
