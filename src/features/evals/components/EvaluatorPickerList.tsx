import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { cn } from '@/utils';
import type { EvaluatorDefinition } from '@/types';

export interface EvaluatorPickerListProps {
  /** Evaluators available for selection. */
  evaluators: EvaluatorDefinition[];
  /** Set of currently selected evaluator ids. */
  selectedIds: Set<string>;
  /** Toggle a single evaluator's selection. */
  onToggle: (id: string) => void;
  /** Select every available evaluator. */
  onSelectAll: () => void;
  /** Clear the selection. */
  onSelectNone: () => void;
  /** Copy shown when no evaluators are configured at all. */
  emptyText?: string;
}

export function EvaluatorPickerList({
  evaluators,
  selectedIds,
  onToggle,
  onSelectAll,
  onSelectNone,
  emptyText = 'No evaluators found for this app.',
}: EvaluatorPickerListProps) {
  const [search, setSearch] = useState('');

  const filteredEvaluators = useMemo(() => {
    if (!search) return evaluators;
    const q = search.toLowerCase();
    return evaluators.filter(
      (e) => e.name.toLowerCase().includes(q) || e.prompt.toLowerCase().includes(q),
    );
  }, [evaluators, search]);

  return (
    <>
      {/* Search + select all/none */}
      <div className="shrink-0 px-6 py-3 border-b border-[var(--border-subtle)] flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--text-muted)]" />
          <input
            type="text"
            placeholder="Search evaluators..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-8 pr-2 py-1.5 text-sm bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-[6px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--border-focus)]"
          />
        </div>
        <button
          onClick={onSelectAll}
          className="text-xs text-[var(--text-brand)] hover:underline shrink-0"
        >
          All
        </button>
        <button
          onClick={onSelectNone}
          className="text-xs text-[var(--text-muted)] hover:underline shrink-0"
        >
          None
        </button>
      </div>

      {/* Evaluator list */}
      <div className="flex-1 overflow-y-auto px-6 py-3 space-y-2">
        {evaluators.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)] text-center py-4">
            {emptyText}
          </p>
        ) : filteredEvaluators.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)] text-center py-4">
            No evaluators match your search.
          </p>
        ) : (
          filteredEvaluators.map((ev) => (
            <label
              key={ev.id}
              className={cn(
                'flex items-start gap-2.5 p-3 rounded-lg cursor-pointer transition-colors',
                selectedIds.has(ev.id)
                  ? 'bg-[var(--surface-info)] border border-[var(--border-info)]'
                  : 'bg-[var(--bg-secondary)] border border-transparent hover:border-[var(--border-subtle)]',
              )}
            >
              <input
                type="checkbox"
                checked={selectedIds.has(ev.id)}
                onChange={() => onToggle(ev.id)}
                className="mt-0.5 rounded accent-[var(--interactive-primary)]"
              />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-[var(--text-primary)]">
                  {ev.name}
                </p>
                <p className="text-xs text-[var(--text-muted)] truncate mt-0.5">
                  {ev.prompt.slice(0, 100)}
                  {ev.prompt.length > 100 ? '...' : ''}
                </p>
                <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-muted)]">
                    {ev.outputSchema?.length ?? 0} field
                    {(ev.outputSchema?.length ?? 0) !== 1 ? 's' : ''}
                  </span>
                  {ev.outputSchema?.slice(0, 3).map((f) => (
                    <span
                      key={f.key}
                      className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-muted)]"
                    >
                      {f.key}
                    </span>
                  ))}
                  {(ev.outputSchema?.length ?? 0) > 3 && (
                    <span className="text-[10px] text-[var(--text-muted)]">
                      +{(ev.outputSchema?.length ?? 0) - 3}
                    </span>
                  )}
                </div>
              </div>
            </label>
          ))
        )}
      </div>
    </>
  );
}
