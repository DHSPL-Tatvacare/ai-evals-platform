import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from '@xyflow/react';
import { X } from 'lucide-react';

import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import { cn } from '@/utils/cn';

interface CustomEdgeData extends Record<string, unknown> {
  /** Human-readable output label (descriptor / branch label). */
  label?: string;
  /** Mirrors the canvas view-vs-edit mode. The hover "×" delete affordance
   *  renders only when true so a published / view-mode canvas never exposes
   *  a destructive one-click on an edge. */
  editable?: boolean;
}

function asEdgeData(value: unknown): CustomEdgeData {
  if (!value || typeof value !== 'object') return {};
  const v = value as Record<string, unknown>;
  return {
    label: typeof v.label === 'string' ? v.label : undefined,
    editable: typeof v.editable === 'boolean' ? v.editable : false,
  };
}

interface CustomEdgeLabelProps {
  edgeId: string;
  label?: string;
  editable: boolean;
  labelX: number;
  labelY: number;
}

/** The label + hover "×" affordance rendered at an edge's midpoint. Split
 *  out from `CustomEdge` so the delete behavior is testable without the
 *  `EdgeLabelRenderer` portal (which only exists inside a fully-measured
 *  `<ReactFlow>`). */
export function CustomEdgeLabel({
  edgeId,
  label,
  editable,
  labelX,
  labelY,
}: CustomEdgeLabelProps) {
  const onDelete = (event: React.MouseEvent) => {
    event.stopPropagation();
    useWorkflowBuilderStore.getState().removeEdge(edgeId);
  };

  return (
    <div
      className="group/edge pointer-events-auto absolute flex items-center gap-1"
      style={{
        transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
      }}
    >
      {label ? (
        <span className="rounded-[var(--radius-default)] bg-[var(--bg-elevated)] px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[var(--text-muted)]">
          {label}
        </span>
      ) : null}
      {editable ? (
        <button
          type="button"
          onClick={onDelete}
          aria-label="Delete edge"
          title="Delete edge"
          className={cn(
            'flex h-4 w-4 items-center justify-center rounded-full',
            'bg-[var(--bg-elevated)] text-[var(--text-muted)]',
            'opacity-0 transition-opacity group-hover/edge:opacity-100',
            'hover:bg-[var(--surface-error)] hover:text-[var(--color-error)]',
          )}
        >
          <X className="h-3 w-3" aria-hidden="true" />
        </button>
      ) : null}
    </div>
  );
}

/** Phase 3 — canvas edge with a hover "×" delete affordance.
 *
 *  Renders the routed output label and, in edit mode, a delete button
 *  centered on the edge that removes it from the store. Removal flows
 *  through `removeEdge`, which keeps the no-orphan-edge invariant intact
 *  (Phase 5 lineage depends on it). The button is the only visible per-edge
 *  delete; Delete / Backspace on a selected edge is wired on the canvas. */
export function CustomEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  style,
  data,
}: EdgeProps) {
  const { label, editable } = asEdgeData(data);
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  return (
    <>
      <BaseEdge id={id} path={edgePath} markerEnd={markerEnd} style={style} />
      <EdgeLabelRenderer>
        <CustomEdgeLabel
          edgeId={id}
          label={label}
          editable={Boolean(editable)}
          labelX={labelX}
          labelY={labelY}
        />
      </EdgeLabelRenderer>
    </>
  );
}
