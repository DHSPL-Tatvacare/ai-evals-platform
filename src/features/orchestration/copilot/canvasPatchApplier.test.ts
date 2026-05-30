/**
 * canvasPatchApplier — pure applier tests.
 *
 * The applier is a pure function over the live builder store: it parses,
 * runs the workflow/version/hash guards, re-validates configs, applies ops,
 * and returns an enriched result. There is no chat callback and no module
 * state. Coverage:
 *   - applies ops in order on hash match, returns changed-id sets
 *   - hydrates add_node `data` from the palette descriptor
 *   - returns the inverse op per applied op (undo contract)
 *   - batches store mutations (one currentDataHash recompute per group)
 *   - aborts mid-stream when AbortSignal fires
 *   - hash mismatch returns `{ kind: 'hash_mismatch', rationale }` and
 *     applies nothing
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import * as snapshotHashModule from '@/features/orchestration/contracts/snapshotHash';
import type { NodeTypeDescriptor } from '@/features/orchestration/types';

import { applyCanvasPatch } from './canvasPatchApplier';

function descriptor(
  nodeType: string,
  displayLabel: string,
  description: string,
): NodeTypeDescriptor {
  return {
    nodeType,
    workflowType: 'crm',
    displayLabel,
    displayCategory: 'routing',
    description,
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

const FIXTURE_CATALOG: NodeTypeDescriptor[] = [
  descriptor('sink.complete', 'Mark complete', 'Ends the run as complete.'),
  descriptor('source.event_trigger', 'Event trigger', 'Starts on an inbound event.'),
];

function seedCatalog() {
  useWorkflowBuilderStore.getState().setPaletteCatalog(FIXTURE_CATALOG);
}

// Empty config is the draft-default for partial authoring — every node
// schema permits it under ``parseNodeConfig({mode: 'draft'})``. The applier
// re-validates every add_node config, so unknown keys (the old contract
// drift case) stay blocked.
function fixturePatch(baseHash: string) {
  return {
    workflow_id: 'wf_demo',
    version_id: null,
    base_data_hash: baseHash,
    rationale: 'demo',
    ops: [
      {
        op: 'add_node',
        node_id: 'n_a',
        payload: { node_type: 'sink.complete', config: {} },
      },
      {
        op: 'add_node',
        node_id: 'n_b',
        payload: { node_type: 'sink.complete', config: {} },
      },
      {
        op: 'add_node',
        node_id: 'n_c',
        payload: {
          node_type: 'source.event_trigger',
          config: {},
        },
      },
      {
        op: 'connect',
        node_id: 'n_a',
        payload: {
          source_node_id: 'n_c',
          output_id: 'default',
          target_node_id: 'n_a',
          edge_id: 'e1',
        },
      },
      {
        op: 'connect',
        node_id: 'n_a',
        payload: {
          source_node_id: 'n_a',
          output_id: 'success',
          target_node_id: 'n_b',
          edge_id: 'e2',
        },
      },
    ],
  };
}

describe('applyCanvasPatch', () => {
  beforeEach(() => {
    useWorkflowBuilderStore.getState().reset();
    seedCatalog();
    vi.restoreAllMocks();
  });

  it('applies ops in order on hash match and returns changed-id sets', async () => {
    const baseHash = useWorkflowBuilderStore.getState().currentDataHash;

    const result = await applyCanvasPatch(fixturePatch(baseHash), {
      staggerMs: 0,
    });

    expect(result.kind).toBe('applied');
    if (result.kind !== 'applied') return;
    expect(result.opsApplied).toBe(5);
    expect(result.rationale).toBe('demo');
    expect(result.addedNodeIds).toEqual(['n_a', 'n_b', 'n_c']);
    expect(result.editedNodeIds).toEqual([]);
    expect(result.removedNodeIds).toEqual([]);
    expect(result.connectEdgeIds).toEqual(['e1', 'e2']);

    const state = useWorkflowBuilderStore.getState();
    expect(state.nodes.map((n) => n.id)).toEqual(['n_a', 'n_b', 'n_c']);
    expect(state.edges.map((e) => e.id)).toEqual(['e1', 'e2']);
  });

  it('hydrates add_node data fields from the palette descriptor', async () => {
    const baseHash = useWorkflowBuilderStore.getState().currentDataHash;

    await applyCanvasPatch(fixturePatch(baseHash), { staggerMs: 0 });

    const state = useWorkflowBuilderStore.getState();
    const nodeA = state.nodes.find((n) => n.id === 'n_a');
    expect(nodeA?.data.label).toBe('Mark complete');
    expect(nodeA?.data.nodeType).toBe('sink.complete');

    const nodeC = state.nodes.find((n) => n.id === 'n_c');
    expect(nodeC?.data.label).toBe('Event trigger');
    expect(nodeC?.data.nodeType).toBe('source.event_trigger');
  });

  it('returns inverse ops that undo each applied op', async () => {
    const baseHash = useWorkflowBuilderStore.getState().currentDataHash;

    const result = await applyCanvasPatch(fixturePatch(baseHash), {
      staggerMs: 0,
    });
    expect(result.kind).toBe('applied');
    if (result.kind !== 'applied') return;

    // One inverse op per applied op, in apply order.
    expect(result.inverse).toHaveLength(5);
    expect(result.inverse[0]).toEqual({ kind: 'remove_node', nodeId: 'n_a' });
    expect(result.inverse[1]).toEqual({ kind: 'remove_node', nodeId: 'n_b' });
    expect(result.inverse[2]).toEqual({ kind: 'remove_node', nodeId: 'n_c' });
    expect(result.inverse[3]).toEqual({ kind: 'remove_edge', edgeId: 'e1' });
    expect(result.inverse[4]).toEqual({ kind: 'remove_edge', edgeId: 'e2' });
  });

  it('captures the prior full config as the update_node_config inverse', async () => {
    const store = useWorkflowBuilderStore.getState();
    store.addNode({
      id: 'n_existing',
      type: 'core.webhook_out',
      position: { x: 0, y: 0 },
      data: {},
      config: { url: 'https://old.example.com/in', method: 'POST' },
    });
    const baseHash = useWorkflowBuilderStore.getState().currentDataHash;

    const result = await applyCanvasPatch(
      {
        workflow_id: 'wf_demo',
        base_data_hash: baseHash,
        ops: [
          {
            op: 'update_node_config',
            node_id: 'n_existing',
            payload: { config_patch: { url: 'https://new.example.com/in' } },
          },
        ],
      },
      { staggerMs: 0 },
    );

    expect(result.kind).toBe('applied');
    if (result.kind !== 'applied') return;
    expect(result.editedNodeIds).toEqual(['n_existing']);
    expect(result.inverse).toEqual([
      {
        kind: 'update_node_config',
        nodeId: 'n_existing',
        config: { url: 'https://old.example.com/in', method: 'POST' },
      },
    ]);

    const updated = useWorkflowBuilderStore
      .getState()
      .nodes.find((n) => n.id === 'n_existing');
    expect(updated?.config).toMatchObject({
      url: 'https://new.example.com/in',
      method: 'POST',
    });
  });

  it('captures the removed node + its edges as the remove_node inverse', async () => {
    const store = useWorkflowBuilderStore.getState();
    store.addNode({
      id: 'n_a',
      type: 'sink.complete',
      position: { x: 5, y: 7 },
      data: { label: 'Mark complete', nodeType: 'sink.complete' },
      config: {},
    });
    store.addNode({
      id: 'n_b',
      type: 'sink.complete',
      position: { x: 0, y: 0 },
      data: {},
      config: {},
    });
    store.addEdge({
      id: 'e_x',
      source: 'n_a',
      target: 'n_b',
      output_id: 'default',
    });
    const baseHash = useWorkflowBuilderStore.getState().currentDataHash;

    const result = await applyCanvasPatch(
      {
        workflow_id: 'wf_demo',
        base_data_hash: baseHash,
        ops: [{ op: 'remove_node', node_id: 'n_a', payload: {} }],
      },
      { staggerMs: 0 },
    );

    expect(result.kind).toBe('applied');
    if (result.kind !== 'applied') return;
    expect(result.removedNodeIds).toEqual(['n_a']);
    expect(result.inverse).toHaveLength(1);
    expect(result.inverse[0]).toEqual({
      kind: 'add_node',
      node: {
        id: 'n_a',
        type: 'sink.complete',
        position: { x: 5, y: 7 },
        data: { label: 'Mark complete', nodeType: 'sink.complete' },
        config: {},
      },
      edges: [{ id: 'e_x', source: 'n_a', target: 'n_b', output_id: 'default' }],
    });

    const state = useWorkflowBuilderStore.getState();
    expect(state.nodes.map((n) => n.id)).toEqual(['n_b']);
    expect(state.edges).toHaveLength(0);
  });

  it('batches add_node ops and connect ops separately (2 hash recomputes)', async () => {
    const baseHash = useWorkflowBuilderStore.getState().currentDataHash;
    const dataHashSpy = vi.spyOn(snapshotHashModule, 'dataSnapshotHash');

    await applyCanvasPatch(fixturePatch(baseHash), { staggerMs: 0 });

    // Three add_node ops collapse into one addNodes call → 1 dataSnapshotHash.
    // Two connect ops collapse into one addEdges call → 1 dataSnapshotHash.
    // Total: exactly 2.
    expect(dataHashSpy).toHaveBeenCalledTimes(2);
  });

  it('returns hash_mismatch with the rationale and applies nothing', async () => {
    const before = {
      nodes: useWorkflowBuilderStore.getState().nodes.length,
      edges: useWorkflowBuilderStore.getState().edges.length,
    };

    const result = await applyCanvasPatch(fixturePatch('h_stale'), {
      staggerMs: 0,
    });

    expect(result.kind).toBe('hash_mismatch');
    if (result.kind !== 'hash_mismatch') return;
    expect(result.rationale).toBe('demo');

    const after = useWorkflowBuilderStore.getState();
    expect(after.nodes).toHaveLength(before.nodes);
    expect(after.edges).toHaveLength(before.edges);
  });

  it('returns parse_error on garbage input', async () => {
    const result = await applyCanvasPatch(
      { ops: 'not-an-array' },
      { staggerMs: 0 },
    );

    expect(result.kind).toBe('parse_error');
  });

  it('aborts remaining ops when AbortSignal fires between groups', async () => {
    const baseHash = useWorkflowBuilderStore.getState().currentDataHash;
    const controller = new AbortController();

    const promise = applyCanvasPatch(fixturePatch(baseHash), {
      staggerMs: 25,
      signal: controller.signal,
    });

    // Abort while the applier is in the inter-group delay before connects.
    setTimeout(() => controller.abort(), 5);

    const result = await promise;
    expect(result.kind).toBe('aborted');
    if (result.kind !== 'aborted') return;
    expect(result.opsApplied).toBe(3);

    const state = useWorkflowBuilderStore.getState();
    expect(state.nodes).toHaveLength(3);
    expect(state.edges).toHaveLength(0);
  });

  it('handles update_node_config by shallow-merging into existing config', async () => {
    const store = useWorkflowBuilderStore.getState();
    store.addNode({
      id: 'n_existing',
      type: 'core.webhook_out',
      position: { x: 0, y: 0 },
      data: {},
      config: { url: 'https://old.example.com/in', method: 'POST' },
    });

    const baseHash = useWorkflowBuilderStore.getState().currentDataHash;

    await applyCanvasPatch(
      {
        workflow_id: 'wf_demo',
        base_data_hash: baseHash,
        ops: [
          {
            op: 'update_node_config',
            node_id: 'n_existing',
            payload: { config_patch: { url: 'https://new.example.com/in' } },
          },
        ],
      },
      { staggerMs: 0 },
    );

    const updated = useWorkflowBuilderStore
      .getState()
      .nodes.find((n) => n.id === 'n_existing');
    expect(updated?.config).toMatchObject({
      url: 'https://new.example.com/in',
      method: 'POST',
    });
  });

  it('handles remove_node and cascades dependent edges', async () => {
    const store = useWorkflowBuilderStore.getState();
    store.addNode({
      id: 'n_a',
      type: 'sink.complete',
      position: { x: 0, y: 0 },
      data: {},
      config: {},
    });
    store.addNode({
      id: 'n_b',
      type: 'sink.complete',
      position: { x: 0, y: 0 },
      data: {},
      config: {},
    });
    store.addEdge({
      id: 'e_x',
      source: 'n_a',
      target: 'n_b',
      output_id: 'default',
    });

    const baseHash = useWorkflowBuilderStore.getState().currentDataHash;

    await applyCanvasPatch(
      {
        workflow_id: 'wf_demo',
        base_data_hash: baseHash,
        ops: [{ op: 'remove_node', node_id: 'n_a', payload: {} }],
      },
      { staggerMs: 0 },
    );

    const state = useWorkflowBuilderStore.getState();
    expect(state.nodes.map((n) => n.id)).toEqual(['n_b']);
    expect(state.edges).toHaveLength(0);
  });
});

describe('applyCanvasPatch — Section 6 guards', () => {
  beforeEach(() => {
    useWorkflowBuilderStore.getState().reset();
    seedCatalog();
    vi.restoreAllMocks();
  });

  it('rejects a patch authored against a different workflow', async () => {
    useWorkflowBuilderStore.getState().setMetadata({
      workflowId: 'wf_A',
      versionId: null,
      name: 'A',
      workflowType: 'crm',
    });
    const baseHash = useWorkflowBuilderStore.getState().currentDataHash;
    const result = await applyCanvasPatch(
      { workflow_id: 'wf_B', base_data_hash: baseHash, ops: [] },
      { staggerMs: 0 },
    );
    expect(result.kind).toBe('workflow_mismatch');
  });

  it('rejects a patch authored against a stale version', async () => {
    useWorkflowBuilderStore.getState().setMetadata({
      workflowId: 'wf_A',
      versionId: 'v_2',
      name: 'A',
      workflowType: 'crm',
    });
    const baseHash = useWorkflowBuilderStore.getState().currentDataHash;
    const result = await applyCanvasPatch(
      {
        workflow_id: 'wf_A',
        version_id: 'v_1',
        base_data_hash: baseHash,
        ops: [],
      },
      { staggerMs: 0 },
    );
    expect(result.kind).toBe('version_mismatch');
  });

  it('rejects add_node when its config has a hard parse issue', async () => {
    useWorkflowBuilderStore.getState().setMetadata({
      workflowId: 'wf_demo',
      versionId: null,
      name: 'demo',
      workflowType: 'crm',
    });
    const baseHash = useWorkflowBuilderStore.getState().currentDataHash;
    const result = await applyCanvasPatch(
      {
        workflow_id: 'wf_demo',
        base_data_hash: baseHash,
        ops: [
          {
            op: 'add_node',
            node_id: 'n_bad',
            payload: {
              node_type: 'sink.complete',
              config: { fabricated_key: 1 },
            },
          },
        ],
      },
      { staggerMs: 0 },
    );
    expect(result.kind).toBe('config_invalid');
    if (result.kind !== 'config_invalid') return;
    expect(result.opKind).toBe('add_node');
    expect(result.nodeId).toBe('n_bad');
    // Nothing landed in the store.
    expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(0);
  });

  it('rejects update_node_config when the merged config has a hard parse issue', async () => {
    const store = useWorkflowBuilderStore.getState();
    store.setMetadata({
      workflowId: 'wf_demo',
      versionId: null,
      name: 'demo',
      workflowType: 'crm',
    });
    store.addNode({
      id: 'n_e',
      type: 'sink.complete',
      position: { x: 0, y: 0 },
      data: {},
      config: { reason: 'ok' },
    });
    const baseHash = useWorkflowBuilderStore.getState().currentDataHash;
    const result = await applyCanvasPatch(
      {
        workflow_id: 'wf_demo',
        base_data_hash: baseHash,
        ops: [
          {
            op: 'update_node_config',
            node_id: 'n_e',
            payload: { config_patch: { fabricated_key: 'x' } },
          },
        ],
      },
      { staggerMs: 0 },
    );
    expect(result.kind).toBe('config_invalid');
    if (result.kind !== 'config_invalid') return;
    expect(result.opKind).toBe('update_node_config');
    // Original config preserved — no partial write landed.
    const node = useWorkflowBuilderStore
      .getState()
      .nodes.find((n) => n.id === 'n_e');
    expect(node?.config).toEqual({ reason: 'ok' });
  });
});
