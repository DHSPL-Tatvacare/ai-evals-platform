/**
 * Page-context selector for the chat widget.
 *
 * Self-contained: NO new context provider, NO prop drilling, NO new global
 * store. Reads the existing `workflowBuilderStore` and the current router
 * location.
 *
 * Two consumers, two entry points:
 *   - `usePageContext()` — React hook (re-renders on relevant changes).
 *     Used by `ChatInput` to render the chip and by tests.
 *   - `getPageContextSnapshot()` — non-hook one-shot getter. Used by the
 *     Zustand `send` action which can't call hooks. Reads via
 *     `useWorkflowBuilderStore.getState()` + `window.location.pathname`.
 *
 * The persistent `canvasContextEnabled` toggle (workflowBuilderStore) gates
 * the snapshot: when off, `getPageContextSnapshot` returns 'none' so the
 * supervisor answers generally and never reads the canvas.
 */
import { useMemo } from 'react';
import { useLocation, matchPath } from 'react-router-dom';

import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';

type WorkflowBuilderStoreState = ReturnType<typeof useWorkflowBuilderStore.getState>;
import type { WorkflowDefinition } from '@/features/orchestration/types';

export type ViewMode = 'view' | 'edit';

export type PageContext =
  | {
      kind: 'orchestration_builder';
      workflowId: string;
      versionId: string | null;
      workflowType: 'crm' | 'clinical';
      appId: string;
      selectedNodeId: string | null;
      definition: WorkflowDefinition;
      dataHash: string;
      viewMode: ViewMode;
      workflowName: string;
    }
  | { kind: 'none' };

const BUILDER_ROUTE_PATTERNS: ReadonlyArray<{ pattern: string; appId: string }> = [
  { pattern: '/inside-sales/orchestration/workflows/:workflowId', appId: 'inside-sales' },
  { pattern: '/kaira/orchestration/workflows/:workflowId', appId: 'kaira-bot' },
  { pattern: '/orchestration/workflows/:workflowId', appId: 'voice-rx' },
];

/** Match the current pathname against the known builder routes. Returns the
 *  resolved app id (so the chat widget threads the same app the canvas
 *  belongs to) or null when off the builder. */
function matchBuilderRoute(pathname: string): { appId: string } | null {
  for (const { pattern, appId } of BUILDER_ROUTE_PATTERNS) {
    if (matchPath({ path: pattern, end: false }, pathname)) {
      return { appId };
    }
  }
  return null;
}

function buildContext(
  pathname: string,
  state: WorkflowBuilderStoreState,
): PageContext {
  if (!state.canvasContextEnabled) return { kind: 'none' };
  const route = matchBuilderRoute(pathname);
  if (!route) return { kind: 'none' };
  if (!state.workflowId || !state.workflowType) return { kind: 'none' };

  const definition: WorkflowDefinition = {
    nodes: state.nodes,
    edges: state.edges,
  };
  if (state.viewport) {
    definition.canvas = { viewport: state.viewport };
  }

  return {
    kind: 'orchestration_builder',
    workflowId: state.workflowId,
    versionId: state.versionId,
    workflowType: state.workflowType,
    appId: route.appId,
    selectedNodeId: state.selectedNodeId,
    definition,
    dataHash: state.currentDataHash,
    viewMode: state.viewMode,
    workflowName: state.workflowName,
  };
}

/** Hook variant — re-renders when the pathname or relevant store fields
 *  change. Returns the builder context whenever the user is on the canvas,
 *  independent of the `canvasContextEnabled` toggle, so the persistent chip
 *  stays mounted and can render its own on/off visuals. The toggle gates only
 *  the wire payload (`getPageContextSnapshot`). Used inside ChatInput / chip /
 *  tests. */
export function usePageContext(): PageContext {
  const { pathname } = useLocation();
  const workflowId = useWorkflowBuilderStore((s) => s.workflowId);
  const versionId = useWorkflowBuilderStore((s) => s.versionId);
  const workflowType = useWorkflowBuilderStore((s) => s.workflowType);
  const workflowName = useWorkflowBuilderStore((s) => s.workflowName);
  const selectedNodeId = useWorkflowBuilderStore((s) => s.selectedNodeId);
  const dataHash = useWorkflowBuilderStore((s) => s.currentDataHash);
  const viewMode = useWorkflowBuilderStore((s) => s.viewMode);
  const nodes = useWorkflowBuilderStore((s) => s.nodes);
  const edges = useWorkflowBuilderStore((s) => s.edges);
  const viewport = useWorkflowBuilderStore((s) => s.viewport);
  // Subscribe so consumers re-render when the canvas toggle flips.
  useWorkflowBuilderStore((s) => s.canvasContextEnabled);

  return useMemo<PageContext>(() => {
    const route = matchBuilderRoute(pathname);
    if (!route) return { kind: 'none' };
    if (!workflowId || !workflowType) return { kind: 'none' };

    const definition: WorkflowDefinition = { nodes, edges };
    if (viewport) {
      definition.canvas = { viewport };
    }

    return {
      kind: 'orchestration_builder',
      workflowId,
      versionId,
      workflowType,
      appId: route.appId,
      selectedNodeId,
      definition,
      dataHash,
      viewMode,
      workflowName,
    };
  }, [
    pathname,
    workflowId,
    versionId,
    workflowType,
    workflowName,
    selectedNodeId,
    dataHash,
    viewMode,
    nodes,
    edges,
    viewport,
  ]);
}

/** Non-hook one-shot snapshot for store actions / event callbacks. Returns
 *  `{ kind: 'none' }` when the user disabled canvas context (toggle off) so
 *  the supervisor answers generally and never reads the canvas. */
export function getPageContextSnapshot(): PageContext {
  const pathname = typeof window !== 'undefined' ? window.location.pathname : '';
  const state = useWorkflowBuilderStore.getState();
  return buildContext(pathname, state);
}
