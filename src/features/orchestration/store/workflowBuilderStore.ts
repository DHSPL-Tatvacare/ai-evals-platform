import { create } from 'zustand';

import type {
  NodeTypeDescriptor,
  WorkflowDefinition,
  WorkflowDefinitionEdge,
  WorkflowDefinitionNode,
} from '@/features/orchestration/types';

interface ViewportState {
  x: number;
  y: number;
  zoom: number;
}

interface WorkflowBuilderState {
  workflowId: string | null;
  versionId: string | null;
  workflowName: string;
  workflowType: 'crm' | 'clinical' | null;
  /** Latest published version on this workflow, or null when never published.
   *  Used by the header to disable Run Now until publish has happened, and to
   *  show a Draft / Published affordance instead of relying on a backend 400. */
  currentPublishedVersionId: string | null;

  nodes: WorkflowDefinitionNode[];
  edges: WorkflowDefinitionEdge[];
  selectedNodeId: string | null;
  /** Persisted React Flow viewport — null until first load/move-end. */
  viewport: ViewportState | null;
  dirty: boolean;

  paletteCatalog: NodeTypeDescriptor[];
  paletteLoading: boolean;

  reset(): void;
  hydrate(definition: WorkflowDefinition): void;
  setMetadata(meta: {
    workflowId: string;
    versionId: string | null;
    name: string;
    workflowType: 'crm' | 'clinical';
    currentPublishedVersionId?: string | null;
  }): void;
  setCurrentPublishedVersionId(versionId: string | null): void;
  setPaletteCatalog(catalog: NodeTypeDescriptor[]): void;
  setPaletteLoading(loading: boolean): void;

  addNode(node: WorkflowDefinitionNode): void;
  updateNodePosition(nodeId: string, position: { x: number; y: number }): void;
  updateNodeConfig(nodeId: string, config: Record<string, unknown>): void;
  removeNode(nodeId: string): void;

  addEdge(edge: WorkflowDefinitionEdge): void;
  removeEdge(edgeId: string): void;

  setSelectedNode(nodeId: string | null): void;
  setViewport(viewport: ViewportState | null): void;

  toDefinition(): WorkflowDefinition;
}

/** Source-prefixed node types whose `config.next_node_id` is the target of
 *  their outgoing default edge. The builder hides this field from the form
 *  and back-fills it at save time so authors don't have to enter node IDs
 *  by hand — the visual edge IS the source of truth. */
export function isSourceNodeType(nodeType: string): boolean {
  return nodeType.startsWith('source.');
}

/** Mutate config of source nodes so `next_node_id` matches their outgoing
 *  default-labelled edge. Returns a fresh nodes array; non-source nodes pass
 *  through untouched. Edges with no label are treated as 'default'. */
export function syncSourceNodeNextEdges(
  nodes: WorkflowDefinitionNode[],
  edges: WorkflowDefinitionEdge[],
): WorkflowDefinitionNode[] {
  return nodes.map((n) => {
    if (!isSourceNodeType(n.type)) return n;
    const defaultEdge =
      edges.find((e) => e.source === n.id && (e.label ?? 'default') === 'default') ??
      edges.find((e) => e.source === n.id);
    if (!defaultEdge) return n;
    return {
      ...n,
      config: { ...n.config, next_node_id: defaultEdge.target },
    };
  });
}

export const useWorkflowBuilderStore = create<WorkflowBuilderState>((set, get) => ({
  workflowId: null,
  versionId: null,
  workflowName: '',
  workflowType: null,
  currentPublishedVersionId: null,

  nodes: [],
  edges: [],
  selectedNodeId: null,
  viewport: null,
  dirty: false,

  paletteCatalog: [],
  paletteLoading: false,

  reset: () =>
    set({
      workflowId: null,
      versionId: null,
      workflowName: '',
      workflowType: null,
      currentPublishedVersionId: null,
      nodes: [],
      edges: [],
      selectedNodeId: null,
      viewport: null,
      dirty: false,
    }),

  hydrate: (definition) =>
    set({
      nodes: definition.nodes ?? [],
      edges: definition.edges ?? [],
      viewport: definition.canvas?.viewport ?? null,
      dirty: false,
      selectedNodeId: null,
    }),

  setMetadata: (meta) =>
    set({
      workflowId: meta.workflowId,
      versionId: meta.versionId,
      workflowName: meta.name,
      workflowType: meta.workflowType,
      currentPublishedVersionId:
        meta.currentPublishedVersionId !== undefined
          ? meta.currentPublishedVersionId
          : get().currentPublishedVersionId,
    }),

  setCurrentPublishedVersionId: (versionId) =>
    set({ currentPublishedVersionId: versionId }),

  setPaletteCatalog: (catalog) => set({ paletteCatalog: catalog }),
  setPaletteLoading: (loading) => set({ paletteLoading: loading }),

  addNode: (node) =>
    set((s) => ({
      nodes: [...s.nodes, node],
      dirty: true,
    })),

  updateNodePosition: (nodeId, position) =>
    set((s) => ({
      nodes: s.nodes.map((n) => (n.id === nodeId ? { ...n, position } : n)),
      dirty: true,
    })),

  updateNodeConfig: (nodeId, config) =>
    set((s) => ({
      nodes: s.nodes.map((n) => (n.id === nodeId ? { ...n, config } : n)),
      dirty: true,
    })),

  removeNode: (nodeId) =>
    set((s) => ({
      nodes: s.nodes.filter((n) => n.id !== nodeId),
      edges: s.edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
      selectedNodeId: s.selectedNodeId === nodeId ? null : s.selectedNodeId,
      dirty: true,
    })),

  addEdge: (edge) =>
    set((s) => ({
      edges: [...s.edges, edge],
      dirty: true,
    })),

  removeEdge: (edgeId) =>
    set((s) => ({
      edges: s.edges.filter((e) => e.id !== edgeId),
      dirty: true,
    })),

  setSelectedNode: (nodeId) => set({ selectedNodeId: nodeId }),

  setViewport: (viewport) => {
    // Updating the viewport must NOT flip dirty; pan/zoom are presentation-
    // only state. Without this guard every wheel-scroll would mark the draft
    // unsaved and re-enable the Save button.
    set({ viewport });
  },

  toDefinition: () => {
    const s = get();
    const nodesWithEdgeBackfill = syncSourceNodeNextEdges(s.nodes, s.edges);
    const definition: WorkflowDefinition = {
      nodes: nodesWithEdgeBackfill,
      edges: s.edges,
    };
    if (s.viewport) {
      definition.canvas = { viewport: s.viewport };
    }
    return definition;
  },
}));
