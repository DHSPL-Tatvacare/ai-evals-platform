import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/services/api/orchestration', () => ({
  resolveUpstreamVariables: vi.fn(),
}));

import { resolveUpstreamVariables } from '@/services/api/orchestration';
import type {
  WorkflowDefinitionEdge,
  WorkflowDefinitionNode,
} from '@/features/orchestration/types';
import { useResolveUpstreamVariables } from './upstreamVariables';

function node(id: string, type: string, config: Record<string, unknown> = {}): WorkflowDefinitionNode {
  return { id, type, position: { x: 0, y: 0 }, data: {}, config };
}
function edge(id: string, source: string, target: string): WorkflowDefinitionEdge {
  return { id, source, target, output_id: 'default' };
}

function wrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children);
}

const NODES = [
  node('src', 'source.cohort', { mode: 'saved' }),
  node('agent', 'llm.extract'),
  node('after', 'voice.place_call'),
];
const EDGES = [edge('e1', 'src', 'agent'), edge('e2', 'agent', 'after')];

describe('useResolveUpstreamVariables', () => {
  beforeEach(() => vi.clearAllMocks());

  it('posts only the upstream subgraph (ancestors + wiring edges)', async () => {
    (resolveUpstreamVariables as ReturnType<typeof vi.fn>).mockResolvedValue({
      fields: [], sample: {}, unresolved: [],
    });
    const { result } = renderHook(
      () =>
        useResolveUpstreamVariables({
          appId: 'inside-sales',
          workflowType: 'crm',
          nodes: NODES,
          edges: EDGES,
          targetNodeId: 'agent',
        }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(resolveUpstreamVariables).toHaveBeenCalledTimes(1);
    const body = (resolveUpstreamVariables as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(body.appId).toBe('inside-sales');
    expect(body.workflowType).toBe('crm');
    expect(body.targetNodeId).toBe('agent');
    expect(body.nodes.map((n: WorkflowDefinitionNode) => n.id)).toEqual(['src']);
    expect(body.edges.map((e: WorkflowDefinitionEdge) => e.id)).toEqual(['e1']);
  });

  it('does not call the resolver when the target has no upstream', () => {
    const { result } = renderHook(
      () =>
        useResolveUpstreamVariables({
          appId: 'inside-sales',
          workflowType: 'crm',
          nodes: [node('agent', 'llm.extract')],
          edges: [],
          targetNodeId: 'agent',
        }),
      { wrapper: wrapper() },
    );
    expect(resolveUpstreamVariables).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('is disabled until appId and targetNodeId are known', () => {
    renderHook(
      () =>
        useResolveUpstreamVariables({
          appId: null,
          workflowType: 'crm',
          nodes: NODES,
          edges: EDGES,
          targetNodeId: 'agent',
        }),
      { wrapper: wrapper() },
    );
    expect(resolveUpstreamVariables).not.toHaveBeenCalled();
  });
});
