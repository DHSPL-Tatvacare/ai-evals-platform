import { beforeEach, describe, expect, it } from 'vitest';

import type { WorkflowDefinitionNode } from '@/features/orchestration/types';

import { useWorkflowBuilderStore } from './workflowBuilderStore';

function fixtureNode(id: string): WorkflowDefinitionNode {
  return {
    id,
    type: 'sink.complete',
    position: { x: 0, y: 0 },
    config: {},
  } as WorkflowDefinitionNode;
}

describe('workflowBuilderStore — spotlight', () => {
  beforeEach(() => {
    useWorkflowBuilderStore.getState().reset();
  });

  it('setSpotlightNode sets and clears the spotlight id', () => {
    expect(useWorkflowBuilderStore.getState().spotlightNodeId).toBeNull();

    useWorkflowBuilderStore.getState().setSpotlightNode('voice.place_call-1');
    expect(useWorkflowBuilderStore.getState().spotlightNodeId).toBe(
      'voice.place_call-1',
    );

    useWorkflowBuilderStore.getState().setSpotlightNode(null);
    expect(useWorkflowBuilderStore.getState().spotlightNodeId).toBeNull();
  });

  it('removeNode clears the spotlight when the spotlighted node is removed', () => {
    useWorkflowBuilderStore.getState().addNode(fixtureNode('a'));
    useWorkflowBuilderStore.getState().setSpotlightNode('a');

    useWorkflowBuilderStore.getState().removeNode('a');
    expect(useWorkflowBuilderStore.getState().spotlightNodeId).toBeNull();
  });

  it('removeNode leaves an unrelated spotlight intact', () => {
    useWorkflowBuilderStore.getState().addNode(fixtureNode('a'));
    useWorkflowBuilderStore.getState().addNode(fixtureNode('b'));
    useWorkflowBuilderStore.getState().setSpotlightNode('b');

    useWorkflowBuilderStore.getState().removeNode('a');
    expect(useWorkflowBuilderStore.getState().spotlightNodeId).toBe('b');
  });

  it('reset clears the spotlight', () => {
    useWorkflowBuilderStore.getState().setSpotlightNode('a');
    useWorkflowBuilderStore.getState().reset();
    expect(useWorkflowBuilderStore.getState().spotlightNodeId).toBeNull();
  });
});
