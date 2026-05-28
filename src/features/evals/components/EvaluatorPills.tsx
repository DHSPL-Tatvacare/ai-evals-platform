import { cn } from '@/utils';

export interface EvaluatorPillsProps {
  /** Selectable evaluators, in display order. */
  items: { id: string; name: string }[];
  /** Currently active evaluator id. */
  activeId: string;
  /** Fired with the clicked evaluator id. */
  onSelect: (id: string) => void;
}

export function EvaluatorPills({ items, activeId, onSelect }: EvaluatorPillsProps) {
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          onClick={() => onSelect(item.id)}
          className={cn(
            'px-2.5 py-1 text-xs rounded-full border transition-colors',
            activeId === item.id
              ? 'border-[var(--border-brand)] bg-[var(--surface-info)] text-[var(--text-brand)]'
              : 'border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]',
          )}
        >
          {item.name}
        </button>
      ))}
    </div>
  );
}
