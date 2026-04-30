import { describe, expect, it, beforeEach } from 'vitest';
import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';

describe('workflowBuilderStore', () => {
  beforeEach(() => {
    useWorkflowBuilderStore.getState().reset();
  });

  it('addNode appends to nodes and marks dirty', () => {
    const s = useWorkflowBuilderStore.getState();
    s.addNode({
      id: 'n1',
      type: 'logic.conditional',
      position: { x: 0, y: 0 },
      data: { label: 'Conditional', nodeType: 'logic.conditional' },
      config: { predicate: { field: 'x', op: 'eq', value: 1 } },
    });
    const s2 = useWorkflowBuilderStore.getState();
    expect(s2.nodes).toHaveLength(1);
    expect(s2.dirty).toBe(true);
  });

  it('updateNodeConfig replaces config and stays dirty', () => {
    const s = useWorkflowBuilderStore.getState();
    s.addNode({
      id: 'n1',
      type: 'logic.wait',
      position: { x: 0, y: 0 },
      data: { label: 'Wait', nodeType: 'logic.wait' },
      config: { duration_hours: 4 },
    });
    s.updateNodeConfig('n1', { duration_hours: 8 });
    const node = useWorkflowBuilderStore.getState().nodes.find((n) => n.id === 'n1');
    expect(node?.config).toEqual({ duration_hours: 8 });
  });

  it('removeNode also removes connected edges', () => {
    const s = useWorkflowBuilderStore.getState();
    s.addNode({
      id: 'a',
      type: 'logic.conditional',
      position: { x: 0, y: 0 },
      data: { label: 'A', nodeType: 'logic.conditional' },
      config: {},
    });
    s.addNode({
      id: 'b',
      type: 'sink.complete',
      position: { x: 0, y: 0 },
      data: { label: 'B', nodeType: 'sink.complete' },
      config: {},
    });
    s.addEdge({ id: 'e1', source: 'a', target: 'b', label: 'true' });
    s.removeNode('a');
    const s2 = useWorkflowBuilderStore.getState();
    expect(s2.nodes).toHaveLength(1);
    expect(s2.edges).toHaveLength(0);
  });

  it('hydrate from a definition resets dirty flag', () => {
    const s = useWorkflowBuilderStore.getState();
    s.addNode({
      id: 'tmp',
      type: 'logic.wait',
      position: { x: 0, y: 0 },
      data: { label: 'Wait', nodeType: 'logic.wait' },
      config: {},
    });
    expect(useWorkflowBuilderStore.getState().dirty).toBe(true);
    s.hydrate({
      nodes: [
        {
          id: 'n1',
          type: 'sink.complete',
          position: { x: 0, y: 0 },
          data: { label: 'End', nodeType: 'sink.complete' },
          config: {},
        },
      ],
      edges: [],
    });
    const s2 = useWorkflowBuilderStore.getState();
    expect(s2.dirty).toBe(false);
    expect(s2.nodes).toHaveLength(1);
  });

  it('toDefinition returns current nodes + edges', () => {
    const s = useWorkflowBuilderStore.getState();
    s.addNode({
      id: 'a',
      type: 'sink.complete',
      position: { x: 1, y: 2 },
      data: { label: 'End', nodeType: 'sink.complete' },
      config: {},
    });
    const def = useWorkflowBuilderStore.getState().toDefinition();
    expect(def.nodes).toHaveLength(1);
    expect(def.edges).toHaveLength(0);
  });
});
