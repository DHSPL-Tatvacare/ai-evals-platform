import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';

import { cn } from '@/utils';

const CATEGORY_COLOR: Record<string, string> = {
  source: 'var(--color-success)',
  filter: 'var(--color-success)',
  logic: 'var(--color-warning)',
  action: 'var(--color-info)',
  escalation: 'var(--color-error)',
  sink: 'var(--text-secondary)',
};

export interface CustomNodeData extends Record<string, unknown> {
  label: string;
  nodeType: string;
  category: string;
  outputEdges: string[];
}

export type CustomNodeType = Node<CustomNodeData, 'custom'>;

export function CustomNode({ data, selected }: NodeProps<CustomNodeType>) {
  const color = CATEGORY_COLOR[data.category] ?? 'var(--text-primary)';
  const outputs = data.outputEdges.length > 0 ? data.outputEdges : ['default'];
  return (
    <div
      className={cn(
        'min-w-44 rounded-[var(--radius-default)] border-2 bg-[var(--bg-elevated)] px-3 py-2 text-sm shadow-sm',
        selected && 'ring-2 ring-[var(--color-brand-accent)]',
      )}
      style={{ borderColor: color }}
    >
      <Handle type="target" position={Position.Top} style={{ background: color }} />
      <div className="font-medium text-[var(--text-primary)]">{data.label}</div>
      <div className="text-xs text-[var(--text-secondary)]">{data.nodeType}</div>
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
