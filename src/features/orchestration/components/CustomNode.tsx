import { Handle, Position, type NodeProps } from '@xyflow/react';

import { getCategoryDef } from '@/features/orchestration/config/categories';
import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import { NodeCard } from './NodeCard';

export type NodeOverlayStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';

export interface NodeOverlay {
  status: NodeOverlayStatus;
  cohortSize?: number;
}

export interface CustomNodeData extends Record<string, unknown> {
  label: string;
  nodeType: string;
  category: string;
  description?: string;
  outputEdges: string[];
  /** Optional run-view overlay. When present, renders a status pill +
   *  cohort-size badge. Set by the run canvas only — never the builder. */
  overlay?: NodeOverlay;
}

function asOverlay(value: unknown): NodeOverlay | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const v = value as Record<string, unknown>;
  const status = v.status;
  if (
    status !== 'pending' &&
    status !== 'running' &&
    status !== 'completed' &&
    status !== 'failed' &&
    status !== 'skipped'
  ) {
    return undefined;
  }
  return {
    status,
    cohortSize: typeof v.cohortSize === 'number' ? v.cohortSize : undefined,
  };
}

function asCustomData(value: unknown): CustomNodeData {
  const fallback: CustomNodeData = {
    label: '',
    nodeType: '',
    category: 'logic',
    outputEdges: ['default'],
  };
  if (!value || typeof value !== 'object') return fallback;
  const v = value as Record<string, unknown>;
  return {
    label: typeof v.label === 'string' ? v.label : fallback.label,
    nodeType: typeof v.nodeType === 'string' ? v.nodeType : fallback.nodeType,
    category: typeof v.category === 'string' ? v.category : fallback.category,
    description: typeof v.description === 'string' ? v.description : undefined,
    outputEdges: Array.isArray(v.outputEdges)
      ? (v.outputEdges as unknown[]).filter((x): x is string => typeof x === 'string')
      : fallback.outputEdges,
    overlay: asOverlay(v.overlay),
  };
}

const OVERLAY_STATUS_COLOR: Record<NodeOverlayStatus, string> = {
  pending: 'var(--text-secondary)',
  running: 'var(--color-info)',
  completed: 'var(--color-success)',
  failed: 'var(--color-error)',
  skipped: 'var(--text-secondary)',
};

const OVERLAY_STATUS_LABEL: Record<NodeOverlayStatus, string> = {
  pending: 'Pending',
  running: 'Running',
  completed: 'Done',
  failed: 'Failed',
  skipped: 'Skipped',
};

const HANDLE_BASE: React.CSSProperties = {
  width: 12,
  height: 6,
  borderRadius: 999,
  border: 0,
};

export function CustomNode({ id, data: rawData, selected }: NodeProps) {
  const data = asCustomData(rawData);
  const cat = getCategoryDef(data.category);
  const outputs = data.outputEdges.length > 0 ? data.outputEdges : ['default'];
  const overlay = data.overlay;

  // Run canvas (overlay present) is read-only; only the builder canvas
  // exposes the per-node delete affordance, which routes through a
  // confirm dialog in the builder page (see WorkflowBuilderPage).
  const onDelete = overlay
    ? undefined
    : () => useWorkflowBuilderStore.getState().requestDeleteNode(id);

  const barTrailing = overlay ? (
    <span
      className="rounded-full border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
      style={{
        borderColor: OVERLAY_STATUS_COLOR[overlay.status],
        color: OVERLAY_STATUS_COLOR[overlay.status],
      }}
    >
      {OVERLAY_STATUS_LABEL[overlay.status]}
    </span>
  ) : null;

  const footer =
    overlay?.cohortSize !== undefined ? (
      <div className="mt-1 text-[11px] text-[var(--text-secondary)]">
        Cohort:{' '}
        <span className="font-semibold text-[var(--text-primary)]">
          {overlay.cohortSize}
        </span>
      </div>
    ) : null;

  const handles = (
    <>
      <Handle
        type="target"
        position={Position.Top}
        style={{ ...HANDLE_BASE, background: cat.accentVar, top: -3 }}
      />
      {outputs.map((label, idx) => (
        <Handle
          key={label}
          type="source"
          position={Position.Bottom}
          id={label}
          style={{
            ...HANDLE_BASE,
            background: cat.accentVar,
            bottom: -3,
            left: `${((idx + 1) / (outputs.length + 1)) * 100}%`,
          }}
        />
      ))}
    </>
  );

  return (
    <NodeCard
      variant="canvas"
      label={data.label}
      description={data.description}
      fallbackSubtitle={data.nodeType}
      category={data.category}
      selected={Boolean(selected)}
      barTrailing={barTrailing}
      footer={footer}
      handles={handles}
      onDelete={onDelete}
    />
  );
}
