/**
 * workflowBuilderStore — canvas-edit state (B3-STORE).
 *
 * Coverage:
 *   - landCanvasPatch is idempotent on partId (a second call is a no-op,
 *     surviving re-render / SSE replay)
 *   - markChanged / clearChanged toggle highlightedNodeIds
 *   - applyInverse replays the recorded inverse in REVERSE order, mapping
 *     each inverse op to the matching store mutation
 *   - canvasContextEnabled toggles via setCanvasContextEnabled
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { dataSnapshotHash } from '@/features/orchestration/contracts/snapshotHash';
import type {
  WorkflowDefinitionEdge,
  WorkflowDefinitionNode,
} from '@/features/orchestration/types';

import { useWorkflowBuilderStore } from './workflowBuilderStore';

function node(id: string): WorkflowDefinitionNode {
  return {
    id,
    type: 'sink.complete',
    position: { x: 0, y: 0 },
    config: {},
  } as WorkflowDefinitionNode;
}

/** Build a patch whose base_data_hash matches the live empty store so the
 *  applier's hash guard passes. Adds one node + connects it from a seeded
 *  source so the applier produces a non-trivial inverse. */
function fixturePatch(baseHash: string) {
  return {
    workflow_id: 'wf_demo',
    version_id: null,
    base_data_hash: baseHash,
    rationale: 'demo',
    ops: [
      {
        op: 'add_node',
        node_id: 'n_new',
        payload: { node_type: 'sink.complete', config: {} },
      },
    ],
  };
}

describe('workflowBuilderStore — canvas edit state', () => {
  beforeEach(() => {
    useWorkflowBuilderStore.getState().reset();
  });

  it('canvasContextEnabled defaults to true and toggles', () => {
    expect(useWorkflowBuilderStore.getState().canvasContextEnabled).toBe(true);
    useWorkflowBuilderStore.getState().setCanvasContextEnabled(false);
    expect(useWorkflowBuilderStore.getState().canvasContextEnabled).toBe(false);
    useWorkflowBuilderStore.getState().setCanvasContextEnabled(true);
    expect(useWorkflowBuilderStore.getState().canvasContextEnabled).toBe(true);
  });

  it('markChanged / clearChanged toggle highlightedNodeIds', () => {
    expect(useWorkflowBuilderStore.getState().highlightedNodeIds.size).toBe(0);

    useWorkflowBuilderStore.getState().markChanged(['a', 'b']);
    const after = useWorkflowBuilderStore.getState().highlightedNodeIds;
    expect(after.has('a')).toBe(true);
    expect(after.has('b')).toBe(true);

    useWorkflowBuilderStore.getState().markChanged(['c']);
    const merged = useWorkflowBuilderStore.getState().highlightedNodeIds;
    expect(merged.has('a')).toBe(true);
    expect(merged.has('c')).toBe(true);

    useWorkflowBuilderStore.getState().clearChanged();
    expect(useWorkflowBuilderStore.getState().highlightedNodeIds.size).toBe(0);
  });

  it('landCanvasPatch records the edit and is idempotent on partId', async () => {
    const baseHash = dataSnapshotHash([], []);
    const patch = fixturePatch(baseHash);

    await useWorkflowBuilderStore
      .getState()
      .landCanvasPatch('part_1', patch, { staggerMs: 0 });

    const edits = useWorkflowBuilderStore.getState().canvasEdits;
    expect(edits['part_1']).toBeDefined();
    expect(edits['part_1'].result.kind).toBe('applied');
    expect(edits['part_1'].changedNodeIds).toContain('n_new');
    // forward op landed the node + flagged it changed
    expect(useWorkflowBuilderStore.getState().nodes.some((n) => n.id === 'n_new')).toBe(
      true,
    );
    expect(useWorkflowBuilderStore.getState().highlightedNodeIds.has('n_new')).toBe(
      true,
    );

    const recordedFirst = edits['part_1'];
    const nodeCountAfterFirst = useWorkflowBuilderStore.getState().nodes.length;

    // Replay with the SAME partId — must be a no-op (no second apply).
    await useWorkflowBuilderStore
      .getState()
      .landCanvasPatch('part_1', patch, { staggerMs: 0 });

    expect(useWorkflowBuilderStore.getState().canvasEdits['part_1']).toBe(
      recordedFirst,
    );
    expect(useWorkflowBuilderStore.getState().nodes.length).toBe(
      nodeCountAfterFirst,
    );
  });

  it('applyInverse replays the recorded inverse in reverse order', () => {
    // Seed a recorded edit by hand so we control the inverse sequence and can
    // assert the store mutations fire in reversed order.
    const inverseEdge: WorkflowDefinitionEdge = {
      id: 'e1',
      source: 's',
      target: 't',
      output_id: 'default',
    } as WorkflowDefinitionEdge;
    const inverse = [
      { kind: 'remove_node' as const, nodeId: 'first' },
      { kind: 'remove_edge' as const, edgeId: 'e_second' },
      {
        kind: 'update_node_config' as const,
        nodeId: 'third',
        config: { foo: 'bar' },
      },
      {
        kind: 'add_node' as const,
        node: node('fourth'),
        edges: [inverseEdge],
      },
    ];

    useWorkflowBuilderStore.setState({
      canvasEdits: {
        part_x: {
          result: { kind: 'applied' } as never,
          inverse,
          changedNodeIds: [],
        },
      },
    });

    const removeNode = vi.spyOn(useWorkflowBuilderStore.getState(), 'removeNode');
    const removeEdge = vi.spyOn(useWorkflowBuilderStore.getState(), 'removeEdge');
    const updateNodeConfig = vi.spyOn(
      useWorkflowBuilderStore.getState(),
      'updateNodeConfig',
    );
    const addNodes = vi.spyOn(useWorkflowBuilderStore.getState(), 'addNodes');
    const addEdges = vi.spyOn(useWorkflowBuilderStore.getState(), 'addEdges');

    const order: string[] = [];
    removeNode.mockImplementation(() => order.push('remove_node'));
    removeEdge.mockImplementation(() => order.push('remove_edge'));
    updateNodeConfig.mockImplementation(() => order.push('update_node_config'));
    addNodes.mockImplementation(() => order.push('add_node'));
    addEdges.mockImplementation(() => order.push('add_edges'));

    useWorkflowBuilderStore.getState().applyInverse('part_x');

    // inverse recorded as [remove_node, remove_edge, update_node_config, add_node]
    // replayed in REVERSE: add_node (addNodes+addEdges) → update_node_config →
    // remove_edge → remove_node.
    expect(order).toEqual([
      'add_node',
      'add_edges',
      'update_node_config',
      'remove_edge',
      'remove_node',
    ]);

    expect(updateNodeConfig).toHaveBeenCalledWith('third', { foo: 'bar' });
    expect(removeEdge).toHaveBeenCalledWith('e_second');
    expect(removeNode).toHaveBeenCalledWith('first');
    expect(addNodes).toHaveBeenCalledWith([node('fourth')]);
    expect(addEdges).toHaveBeenCalledWith([inverseEdge]);
  });

  it('applyInverse is a no-op for an unknown partId', () => {
    expect(() =>
      useWorkflowBuilderStore.getState().applyInverse('nope'),
    ).not.toThrow();
  });
});
