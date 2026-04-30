import type { DragEvent } from 'react';

import { cn } from '@/utils';
import type { NodeTypeDescriptor } from '@/features/orchestration/types';

const CATEGORY_COLOR: Record<string, string> = {
  source: 'var(--color-success)',
  filter: 'var(--color-success)',
  logic: 'var(--color-warning)',
  action: 'var(--color-info)',
  escalation: 'var(--color-error)',
  sink: 'var(--text-secondary)',
};

export function PaletteItem({ desc }: { desc: NodeTypeDescriptor }) {
  const onDragStart = (event: DragEvent<HTMLDivElement>) => {
    event.dataTransfer.setData('application/orchestration-node', JSON.stringify(desc));
    event.dataTransfer.effectAllowed = 'move';
  };
  return (
    <div
      draggable
      onDragStart={onDragStart}
      className={cn(
        'cursor-grab rounded-[var(--radius-default)] border bg-[var(--bg-elevated)] px-2 py-1 text-xs shadow-sm',
      )}
      style={{ borderColor: CATEGORY_COLOR[desc.category] ?? 'var(--border-default)' }}
      title={desc.description}
    >
      <div className="font-medium text-[var(--text-primary)]">{desc.label}</div>
      <div className="text-[10px] text-[var(--text-secondary)]">{desc.nodeType}</div>
    </div>
  );
}
