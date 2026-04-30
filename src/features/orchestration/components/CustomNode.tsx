import { Handle, Position, type NodeProps } from '@xyflow/react';

import { cn } from '@/utils';

const CATEGORY_COLOR: Record<string, string> = {
  source: 'var(--color-success)',
  filter: 'var(--color-success)',
  logic: 'var(--color-warning)',
  action: 'var(--color-info)',
  escalation: 'var(--color-error)',
  sink: 'var(--text-secondary)',
};

export type NodeOverlayStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';

export interface NodeOverlay {
  status: NodeOverlayStatus;
  cohortSize?: number;
}

export interface CustomNodeData extends Record<string, unknown> {
  label: string;
  nodeType: string;
  category: string;
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

export function CustomNode({ data: rawData, selected }: NodeProps) {
  const data = asCustomData(rawData);
  const color = CATEGORY_COLOR[data.category] ?? 'var(--text-primary)';
  const outputs = data.outputEdges.length > 0 ? data.outputEdges : ['default'];
  const overlay = data.overlay;
  return (
    <div
      className={cn(
        'min-w-44 rounded-[var(--radius-default)] border-2 bg-[var(--bg-elevated)] px-3 py-2 text-sm shadow-sm',
        selected && 'ring-2 ring-[var(--color-brand-accent)]',
      )}
      style={{ borderColor: color }}
    >
      <Handle type="target" position={Position.Top} style={{ background: color }} />
      <div className="flex items-center justify-between gap-2">
        <div className="font-medium text-[var(--text-primary)]">{data.label}</div>
        {overlay ? (
          <span
            className="rounded-full border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
            style={{
              borderColor: OVERLAY_STATUS_COLOR[overlay.status],
              color: OVERLAY_STATUS_COLOR[overlay.status],
            }}
          >
            {OVERLAY_STATUS_LABEL[overlay.status]}
          </span>
        ) : null}
      </div>
      <div className="text-xs text-[var(--text-secondary)]">{data.nodeType}</div>
      {overlay?.cohortSize !== undefined ? (
        <div className="mt-1 text-[11px] text-[var(--text-secondary)]">
          Cohort: <span className="font-semibold text-[var(--text-primary)]">{overlay.cohortSize}</span>
        </div>
      ) : null}
      {outputs.map((label, idx) => (
        <Handle
          key={label}
          type="source"
          position={Position.Bottom}
          id={label}
          style={{
            background: color,
            left: `${((idx + 1) / (outputs.length + 1)) * 100}%`,
          }}
        />
      ))}
    </div>
  );
}
