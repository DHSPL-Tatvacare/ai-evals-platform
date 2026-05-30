/**
 * canvasPatchApplier — hash-mismatch (rebase) tests.
 *
 * The applier is pure: on a stale `base_data_hash` it applies nothing and
 * returns `{ kind: 'hash_mismatch', rationale }`. The caller (chat widget)
 * owns whatever rebase prompt or redo flow it wants — the applier no longer
 * holds module state or a "yes, redo" text path.
 *
 * Coverage:
 *   - stale hash returns hash_mismatch carrying the patch rationale verbatim
 *   - nothing lands in the store on mismatch
 *   - a matching hash on the next call applies cleanly (no carried state)
 *   - each mismatch reports its own rationale independently
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import type { NodeTypeDescriptor } from '@/features/orchestration/types';

import { applyCanvasPatch } from './canvasPatchApplier';

function descriptor(nodeType: string, displayLabel: string): NodeTypeDescriptor {
  return {
    nodeType,
    workflowType: 'crm',
    displayLabel,
    displayCategory: 'routing',
    description: '',
    authoringStatus: 'active',
    configSchema: {},
    editorHints: {},
    requiredPayloadFields: [],
    emittedPayloadFields: [],
    outputEdges: [],
    graphRules: {},
    runtimeContract: { executionKind: 'routing' },
    category: 'sink',
    label: displayLabel,
  } as NodeTypeDescriptor;
}

function seedCatalog() {
  useWorkflowBuilderStore.getState().setPaletteCatalog([
    descriptor('sink.complete', 'Mark complete'),
    descriptor('source.event_trigger', 'Event trigger'),
  ]);
}

function fixturePatch(baseHash: string, rationale: string) {
  return {
    workflow_id: 'wf_demo',
    version_id: null,
    base_data_hash: baseHash,
    rationale,
    ops: [
      {
        op: 'add_node',
        node_id: 'n_a',
        payload: { node_type: 'sink.complete', config: {} },
      },
      {
        op: 'add_node',
        node_id: 'n_c',
        payload: { node_type: 'source.event_trigger', config: {} },
      },
    ],
  };
}

describe('canvasPatchApplier — hash mismatch', () => {
  beforeEach(() => {
    useWorkflowBuilderStore.getState().reset();
    seedCatalog();
    vi.restoreAllMocks();
  });

  it('returns hash_mismatch carrying the rationale and applies nothing', async () => {
    const result = await applyCanvasPatch(
      fixturePatch('stale-hash', 'add cohort + sink chain'),
      { staggerMs: 0 },
    );

    expect(result.kind).toBe('hash_mismatch');
    if (result.kind !== 'hash_mismatch') return;
    expect(result.rationale).toBe('add cohort + sink chain');

    const state = useWorkflowBuilderStore.getState();
    expect(state.nodes).toHaveLength(0);
    expect(state.edges).toHaveLength(0);
  });

  it('carries each mismatch rationale independently', async () => {
    const first = await applyCanvasPatch(
      fixturePatch('stale-hash', 'first-attempt'),
      { staggerMs: 0 },
    );
    const second = await applyCanvasPatch(
      fixturePatch('still-stale', 'second-attempt'),
      { staggerMs: 0 },
    );

    expect(first.kind).toBe('hash_mismatch');
    if (first.kind === 'hash_mismatch') {
      expect(first.rationale).toBe('first-attempt');
    }
    expect(second.kind).toBe('hash_mismatch');
    if (second.kind === 'hash_mismatch') {
      expect(second.rationale).toBe('second-attempt');
    }
  });

  it('applies cleanly on the next call once the hash matches (no carried state)', async () => {
    const mismatch = await applyCanvasPatch(
      fixturePatch('stale-hash', 'rationale-C'),
      { staggerMs: 0 },
    );
    expect(mismatch.kind).toBe('hash_mismatch');

    const baseHash = useWorkflowBuilderStore.getState().currentDataHash;
    const result = await applyCanvasPatch(
      fixturePatch(baseHash, 'rationale-D'),
      { staggerMs: 0 },
    );
    expect(result.kind).toBe('applied');
    if (result.kind !== 'applied') return;
    expect(result.addedNodeIds).toEqual(['n_a', 'n_c']);
  });
});
