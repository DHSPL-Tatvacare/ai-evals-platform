import { describe, expect, it } from 'vitest';

import {
  deriveOutputEdges,
  deriveOutputEdgeLabels,
} from '@/features/orchestration/components/Canvas';
import type { WorkflowDefinitionNode } from '@/features/orchestration/types';

function node(type: string, config: Record<string, unknown>): WorkflowDefinitionNode {
  return {
    id: 'n1',
    type,
    position: { x: 0, y: 0 },
    data: { label: type },
    config,
  } as WorkflowDefinitionNode;
}

describe('deriveOutputEdges', () => {
  it('conditional renders one handle per branch plus default', () => {
    const n = node('logic.conditional', {
      branches: [
        { id: 'Branch_1_1', label: 'pb1' },
        { id: 'Branch_2_2', label: 'pb2' },
      ],
    });
    expect(deriveOutputEdges(n, undefined)).toEqual(['Branch_1_1', 'Branch_2_2', 'default']);
  });

  it('conditional with no branches still shows default', () => {
    expect(deriveOutputEdges(node('logic.conditional', { branches: [] }), undefined)).toEqual([
      'default',
    ]);
  });

  it('split percentage with holdout adds a control handle', () => {
    const n = node('logic.split', {
      mode: 'percentage',
      holdout_percent: 20,
      branches: [{ id: 'a' }, { id: 'b' }],
    });
    expect(deriveOutputEdges(n, undefined)).toEqual(['a', 'b', 'control']);
  });
});

describe('deriveOutputEdgeLabels', () => {
  it('conditional labels branches and Default', () => {
    const n = node('logic.conditional', { branches: [{ id: 'Branch_1_1', label: 'pb1' }] });
    expect(deriveOutputEdgeLabels(n, undefined)).toEqual({ Branch_1_1: 'pb1', default: 'Default' });
  });
});
