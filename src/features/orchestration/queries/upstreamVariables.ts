/**
 * Upstream-variable resolution hook for the AI agent Input pane. Server data
 * via apiQueryFn (the 401-refresh-and-retry flow stays in effect), keyed on a
 * hash of the upstream subgraph so it refetches only when an ancestor changes.
 */
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import {
  resolveUpstreamVariables,
  type ResolveUpstreamVariablesResponse,
} from '@/services/api/orchestration';
import {
  extractUpstreamSubgraph,
  type UpstreamSubgraph,
} from '@/features/orchestration/components/inspector/upstreamVariables';
import type {
  WorkflowDefinitionEdge,
  WorkflowDefinitionNode,
  WorkflowType,
} from '@/features/orchestration/types';

export const upstreamVariableKeys = {
  resolve: (
    appId: string,
    workflowType: string,
    targetNodeId: string,
    subgraph: UpstreamSubgraph,
  ) =>
    [
      'orchestration',
      'upstream-variables',
      appId,
      workflowType,
      targetNodeId,
      subgraph,
    ] as const,
};

export function useResolveUpstreamVariables(params: {
  appId: string | null | undefined;
  workflowType: WorkflowType | null | undefined;
  nodes: readonly WorkflowDefinitionNode[];
  edges: readonly WorkflowDefinitionEdge[];
  targetNodeId: string | null | undefined;
}) {
  const { appId, workflowType, nodes, edges, targetNodeId } = params;

  const subgraph = useMemo(
    () => extractUpstreamSubgraph(targetNodeId ?? '', nodes, edges),
    [targetNodeId, nodes, edges],
  );

  return useQuery<ResolveUpstreamVariablesResponse>({
    queryKey: upstreamVariableKeys.resolve(
      appId ?? '',
      workflowType ?? '',
      targetNodeId ?? '',
      subgraph,
    ),
    queryFn: () =>
      resolveUpstreamVariables({
        appId: appId as string,
        workflowType: workflowType as WorkflowType,
        nodes: subgraph.nodes,
        edges: subgraph.edges,
        targetNodeId: targetNodeId as string,
      }),
    enabled:
      Boolean(appId && workflowType && targetNodeId) && subgraph.nodes.length > 0,
    staleTime: 30_000,
  });
}
