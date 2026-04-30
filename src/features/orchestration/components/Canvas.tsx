import {
  Background,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type Viewport,
} from '@xyflow/react';
import { useCallback, useEffect, useMemo, useRef, type DragEvent } from 'react';
import '@xyflow/react/dist/style.css';

import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import type {
  NodeTypeDescriptor,
  WorkflowDefinitionNode,
} from '@/features/orchestration/types';
import { CustomNode } from './CustomNode';

const nodeTypes = { custom: CustomNode };

/** Derive the runtime output-handle labels for a node.
 *
 * Most nodes carry static handles from their palette descriptor
 * (`outputEdges`). `logic.split` is special: branch labels live in
 * `config.branches[*].label`, so the canvas must recompute them per node
 * config — the static descriptor for split is empty and would otherwise
 * collapse into a single `default` handle. */
function deriveOutputEdges(
  node: WorkflowDefinitionNode,
  desc: NodeTypeDescriptor | undefined,
): string[] {
  if (node.type === 'logic.split') {
    const branches = (node.config?.branches as Array<{ label?: string }> | undefined) ?? [];
    const labels = branches
      .map((b) => (typeof b?.label === 'string' ? b.label.trim() : ''))
      .filter((s) => s.length > 0);
    if (labels.length > 0) return labels;
  }
  const fromDesc = desc?.outputEdges ?? [];
  return fromDesc.length > 0 ? fromDesc : ['default'];
}

export function Canvas() {
  return (
    <ReactFlowProvider>
      <CanvasInner />
    </ReactFlowProvider>
  );
}

function CanvasInner() {
  const nodes = useWorkflowBuilderStore((s) => s.nodes);
  const edges = useWorkflowBuilderStore((s) => s.edges);
  const palette = useWorkflowBuilderStore((s) => s.paletteCatalog);
  const savedViewport = useWorkflowBuilderStore((s) => s.viewport);

  const reactFlow = useReactFlow();
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  // Track whether we've already restored the saved viewport; one-shot per mount
  // so a later store update during the same session doesn't snap-back the user's
  // manual pan/zoom.
  const viewportRestored = useRef(false);

  const rfNodes: Node[] = useMemo(
    () =>
      nodes.map((n) => {
        const desc = palette.find((p) => p.nodeType === n.type);
        return {
          id: n.id,
          type: 'custom',
          position: n.position,
          data: {
            label: desc?.label ?? n.type,
            nodeType: n.type,
            category: desc?.category ?? 'logic',
            outputEdges: deriveOutputEdges(n, desc),
          },
        };
      }),
    [nodes, palette],
  );

  const rfEdges: Edge[] = useMemo(
    () =>
      edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: e.label,
        label: e.label,
      })),
    [edges],
  );

  // Restore saved viewport once the ReactFlow instance is ready. Falls back to
  // fitView (via the ReactFlow `fitView` prop below) when no viewport exists.
  useEffect(() => {
    if (viewportRestored.current) return;
    if (!savedViewport) return;
    reactFlow.setViewport(savedViewport);
    viewportRestored.current = true;
  }, [savedViewport, reactFlow]);

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    const s = useWorkflowBuilderStore.getState();
    for (const c of changes) {
      if (c.type === 'position' && c.position) {
        s.updateNodePosition(c.id, c.position);
      } else if (c.type === 'remove') {
        s.removeNode(c.id);
      } else if (c.type === 'select') {
        s.setSelectedNode(c.selected ? c.id : null);
      }
    }
  }, []);

  const onEdgesChange = useCallback((changes: EdgeChange[]) => {
    const s = useWorkflowBuilderStore.getState();
    for (const c of changes) {
      if (c.type === 'remove') s.removeEdge(c.id);
    }
  }, []);

  const onConnect = useCallback((conn: Connection) => {
    const s = useWorkflowBuilderStore.getState();
    if (!conn.source || !conn.target) return;
    s.addEdge({
      id: `e-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      source: conn.source,
      target: conn.target,
      label: conn.sourceHandle ?? 'default',
    });
  }, []);

  const onMoveEnd = useCallback(
    (_event: unknown, viewport: Viewport) => {
      // Persist viewport in store so the next reload reopens at the user's
      // last pan/zoom. setViewport does NOT mark the draft dirty.
      useWorkflowBuilderStore.getState().setViewport({
        x: viewport.x,
        y: viewport.y,
        zoom: viewport.zoom,
      });
    },
    [],
  );

  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      const dataStr = event.dataTransfer.getData('application/orchestration-node');
      if (!dataStr) return;
      let desc: NodeTypeDescriptor;
      try {
        desc = JSON.parse(dataStr) as NodeTypeDescriptor;
      } catch {
        return;
      }
      // Convert browser-coords (event.clientX/Y) to React Flow's transformed
      // pane-coords. Bare bounds-math drops nodes in the wrong place under
      // any pan/zoom; screenToFlowPosition is the React Flow primitive that
      // handles the coordinate transform.
      const position = reactFlow.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });
      useWorkflowBuilderStore.getState().addNode({
        id: `${desc.nodeType}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        type: desc.nodeType,
        position,
        data: { label: desc.label, nodeType: desc.nodeType },
        config: {},
      });
    },
    [reactFlow],
  );

  const onDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  return (
    <div ref={wrapperRef} className="h-full w-full" onDrop={onDrop} onDragOver={onDragOver}>
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onMoveEnd={onMoveEnd}
        // Only autofit when there's no saved viewport; once the user has
        // panned/zoomed at least once, restoring fitView would discard that.
        fitView={savedViewport == null}
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
