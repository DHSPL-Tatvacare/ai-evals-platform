import { create } from 'zustand';

import type {
  NodeTypeDescriptor,
  WorkflowDefinition,
  WorkflowDefinitionEdge,
  WorkflowDefinitionNode,
} from '@/features/orchestration/types';

interface WorkflowBuilderState {
  workflowId: string | null;
  versionId: string | null;
  workflowName: string;
  workflowType: 'crm' | 'clinical' | null;

  nodes: WorkflowDefinitionNode[];
  edges: WorkflowDefinitionEdge[];
  selectedNodeId: string | null;
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
  }): void;
  setPaletteCatalog(catalog: NodeTypeDescriptor[]): void;
  setPaletteLoading(loading: boolean): void;

  addNode(node: WorkflowDefinitionNode): void;
  updateNodePosition(nodeId: string, position: { x: number; y: number }): void;
  updateNodeConfig(nodeId: string, config: Record<string, unknown>): void;
  removeNode(nodeId: string): void;

  addEdge(edge: WorkflowDefinitionEdge): void;
  removeEdge(edgeId: string): void;

  setSelectedNode(nodeId: string | null): void;

  toDefinition(): WorkflowDefinition;
}

export const useWorkflowBuilderStore = create<WorkflowBuilderState>((set, get) => ({
  workflowId: null,
  versionId: null,
  workflowName: '',
  workflowType: null,

  nodes: [],
  edges: [],
  selectedNodeId: null,
  dirty: false,

  paletteCatalog: [],
  paletteLoading: false,

  reset: () =>
    set({
      workflowId: null,
      versionId: null,
      workflowName: '',
      workflowType: null,
      nodes: [],
      edges: [],
      selectedNodeId: null,
      dirty: false,
    }),

  hydrate: (definition) =>
    set({
      nodes: definition.nodes ?? [],
      edges: definition.edges ?? [],
      dirty: false,
      selectedNodeId: null,
    }),

  setMetadata: (meta) =>
    set({
      workflowId: meta.workflowId,
      versionId: meta.versionId,
      workflowName: meta.name,
      workflowType: meta.workflowType,
    }),

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

  toDefinition: () => {
    const s = get();
    return { nodes: s.nodes, edges: s.edges };
  },
}));
