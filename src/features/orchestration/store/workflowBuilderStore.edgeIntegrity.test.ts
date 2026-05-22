/**
 * Phase 3 — canvas edge integrity.
 *
 * The bug class: edges silently defaulting `output_id` to 'default', and
 * dangling edges left pointing at a removed branch output. Both break the
 * backend's per-run node-step lineage (Phase 5). These tests pin the store
 * guards: connect rejects a handle-less connection, blocks a duplicate
 * (node, output_id) unless the descriptor allows fan-out, reconnect
 * re-points an edge, and removing a branch prunes its dangling edge.
 */
import { beforeEach, describe, expect, it } from 'vitest';

import type {
  NodeTypeDescriptor,
  WorkflowDefinitionNode,
} from '@/features/orchestration/types';
import { getEdgeOutputId } from '@/features/orchestration/types';

import { useWorkflowBuilderStore } from './workflowBuilderStore';

function node(id: string, type: string, config: Record<string, unknown> = {}): WorkflowDefinitionNode {
  return { id, type, position: { x: 0, y: 0 }, config } as WorkflowDefinitionNode;
}

function descriptor(
  nodeType: string,
  outputEdges: NodeTypeDescriptor['outputEdges'],
  graphRules: NodeTypeDescriptor['graphRules'] = {},
): NodeTypeDescriptor {
  return {
    nodeType,
    workflowType: 'crm',
    displayLabel: nodeType,
    displayCategory: 'routing',
    description: '',
    authoringStatus: 'active',
    configSchema: {},
    editorHints: {},
    requiredPayloadFields: [],
    emittedPayloadFields: [],
    outputEdges,
    graphRules,
    runtimeContract: { executionKind: 'routing' },
    category: 'logic',
    label: nodeType,
  } as NodeTypeDescriptor;
}

describe('workflowBuilderStore — connectEdge guard', () => {
  beforeEach(() => {
    useWorkflowBuilderStore.getState().reset();
    useWorkflowBuilderStore.getState().setViewMode('edit');
  });

  it('rejects a connection with no sourceHandle instead of writing default', () => {
    const s = useWorkflowBuilderStore.getState();
    s.addNodes([node('a', 'action.send'), node('b', 'sink.complete')]);
    const result = s.connectEdge({ source: 'a', target: 'b', sourceHandle: null, targetHandle: null });
    expect(result.ok).toBe(false);
    expect(useWorkflowBuilderStore.getState().edges).toHaveLength(0);
  });

  it('writes the branch output_id from sourceHandle (never default)', () => {
    const s = useWorkflowBuilderStore.getState();
    s.setPaletteCatalog([
      descriptor('logic.conditional', []),
      descriptor('sink.complete', []),
    ]);
    s.addNodes([
      node('cond', 'logic.conditional', { branches: [{ id: 'vip', label: 'VIP' }] }),
      node('b', 'sink.complete'),
    ]);
    const result = s.connectEdge({ source: 'cond', target: 'b', sourceHandle: 'vip', targetHandle: null });
    expect(result.ok).toBe(true);
    const edges = useWorkflowBuilderStore.getState().edges;
    expect(edges).toHaveLength(1);
    expect(getEdgeOutputId(edges[0])).toBe('vip');
  });

  it('blocks a duplicate edge for the same (node, output_id) when the handle is single-binding', () => {
    const s = useWorkflowBuilderStore.getState();
    s.setPaletteCatalog([
      descriptor('action.send', [
        { id: 'success', label: 'Success', cardinality: 'one', dynamic: false },
      ]),
      descriptor('sink.complete', []),
    ]);
    s.addNodes([
      node('a', 'action.send'),
      node('b', 'sink.complete'),
      node('c', 'sink.complete'),
    ]);
    const first = s.connectEdge({ source: 'a', target: 'b', sourceHandle: 'success', targetHandle: null });
    const second = s.connectEdge({ source: 'a', target: 'c', sourceHandle: 'success', targetHandle: null });
    expect(first.ok).toBe(true);
    expect(second.ok).toBe(false);
    expect(useWorkflowBuilderStore.getState().edges).toHaveLength(1);
  });

  it('allows a second edge on the same output when the handle declares fan-out', () => {
    const s = useWorkflowBuilderStore.getState();
    s.setPaletteCatalog([
      descriptor('source.cohort', [
        { id: 'default', label: 'Default', cardinality: 'many', dynamic: false },
      ]),
      descriptor('sink.complete', []),
    ]);
    s.addNodes([
      node('src', 'source.cohort'),
      node('b', 'sink.complete'),
      node('c', 'sink.complete'),
    ]);
    const first = s.connectEdge({ source: 'src', target: 'b', sourceHandle: 'default', targetHandle: null });
    const second = s.connectEdge({ source: 'src', target: 'c', sourceHandle: 'default', targetHandle: null });
    expect(first.ok).toBe(true);
    expect(second.ok).toBe(true);
    expect(useWorkflowBuilderStore.getState().edges).toHaveLength(2);
  });
});

describe('workflowBuilderStore — reconnectEdge', () => {
  beforeEach(() => {
    useWorkflowBuilderStore.getState().reset();
    useWorkflowBuilderStore.getState().setViewMode('edit');
  });

  it('re-points an existing edge to a new target and output_id', () => {
    const s = useWorkflowBuilderStore.getState();
    s.setPaletteCatalog([descriptor('action.send', []), descriptor('sink.complete', [])]);
    s.addNodes([
      node('a', 'action.send'),
      node('b', 'sink.complete'),
      node('c', 'sink.complete'),
    ]);
    s.connectEdge({ source: 'a', target: 'b', sourceHandle: 'success', targetHandle: null });
    const edgeId = useWorkflowBuilderStore.getState().edges[0].id;
    const result = s.reconnectEdge(edgeId, {
      source: 'a',
      target: 'c',
      sourceHandle: 'failed',
      targetHandle: null,
    });
    expect(result.ok).toBe(true);
    const edges = useWorkflowBuilderStore.getState().edges;
    expect(edges).toHaveLength(1);
    expect(edges[0].target).toBe('c');
    expect(getEdgeOutputId(edges[0])).toBe('failed');
  });

  it('rejects a reconnect that drops the sourceHandle', () => {
    const s = useWorkflowBuilderStore.getState();
    s.addNodes([node('a', 'action.send'), node('b', 'sink.complete')]);
    s.connectEdge({ source: 'a', target: 'b', sourceHandle: 'success', targetHandle: null });
    const edgeId = useWorkflowBuilderStore.getState().edges[0].id;
    const result = s.reconnectEdge(edgeId, {
      source: 'a',
      target: 'b',
      sourceHandle: null,
      targetHandle: null,
    });
    expect(result.ok).toBe(false);
    // Original edge stays intact.
    expect(getEdgeOutputId(useWorkflowBuilderStore.getState().edges[0])).toBe('success');
  });
});

describe('workflowBuilderStore — branch-delete edge cleanup', () => {
  beforeEach(() => {
    useWorkflowBuilderStore.getState().reset();
    useWorkflowBuilderStore.getState().setViewMode('edit');
    useWorkflowBuilderStore.getState().setPaletteCatalog([
      descriptor('logic.conditional', []),
      descriptor('sink.complete', []),
    ]);
  });

  it('prunes the edge bound to a removed conditional branch', () => {
    const s = useWorkflowBuilderStore.getState();
    s.addNodes([
      node('cond', 'logic.conditional', {
        branches: [
          { id: 'vip', label: 'VIP', predicate: { field: 'x', op: 'eq', value: '1' } },
          { id: 'rest', label: 'Rest', predicate: { field: 'y', op: 'eq', value: '2' } },
        ],
      }),
      node('b', 'sink.complete'),
      node('c', 'sink.complete'),
    ]);
    s.connectEdge({ source: 'cond', target: 'b', sourceHandle: 'vip', targetHandle: null });
    s.connectEdge({ source: 'cond', target: 'c', sourceHandle: 'rest', targetHandle: null });
    expect(useWorkflowBuilderStore.getState().edges).toHaveLength(2);

    // Remove the 'vip' branch via the config write — the cleanup must drop
    // the edge whose output_id was 'vip', leaving 'rest' intact.
    s.updateNodeConfig('cond', {
      branches: [{ id: 'rest', label: 'Rest', predicate: { field: 'y', op: 'eq', value: '2' } }],
    });
    const edges = useWorkflowBuilderStore.getState().edges;
    expect(edges).toHaveLength(1);
    expect(getEdgeOutputId(edges[0])).toBe('rest');
    expect(edges.some((e) => getEdgeOutputId(e) === 'vip')).toBe(false);
  });

  it('keeps the always-present default edge when branches change', () => {
    const s = useWorkflowBuilderStore.getState();
    s.addNodes([
      node('cond', 'logic.conditional', { branches: [{ id: 'vip', label: 'VIP' }] }),
      node('b', 'sink.complete'),
    ]);
    s.connectEdge({ source: 'cond', target: 'b', sourceHandle: 'default', targetHandle: null });
    s.updateNodeConfig('cond', { branches: [] });
    const edges = useWorkflowBuilderStore.getState().edges;
    expect(edges).toHaveLength(1);
    expect(getEdgeOutputId(edges[0])).toBe('default');
  });
});
