import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, CircleDashed, CircleDot, TableProperties } from 'lucide-react';

import { cn } from '@/utils';

import type { CsvFieldDef } from '../types';

interface CsvFieldCalloutProps<TGroup extends string = string> {
  schema: CsvFieldDef<TGroup>[];
  title?: string;
  groupLabels?: Partial<Record<TGroup, string>>;
  groupOrder?: TGroup[];
}

function humanizeLabel(value: string): string {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

export function CsvFieldCallout<TGroup extends string = string>({
  schema,
  title = 'Required CSV Format',
  groupLabels,
  groupOrder,
}: CsvFieldCalloutProps<TGroup>) {
  const [expanded, setExpanded] = useState(false);
  const requiredCount = schema.filter((field) => field.required).length;

  const resolvedGroupOrder = useMemo(() => {
    if (groupOrder && groupOrder.length > 0) {
      return groupOrder;
    }

    return Array.from(new Set(schema.map((field) => field.group)));
  }, [groupOrder, schema]);

  return (
    <div className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)]/50 overflow-hidden">
      <button
        onClick={() => setExpanded((current) => !current)}
        className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left hover:bg-[var(--bg-secondary)] transition-colors"
      >
        <TableProperties className="h-4 w-4 text-[var(--color-info)] shrink-0" />
        <div className="flex-1 min-w-0">
          <span className="text-[13px] font-medium text-[var(--text-primary)]">
            {title}
          </span>
          <span className="ml-2 text-[11px] text-[var(--text-muted)]">
            {requiredCount} required, {schema.length - requiredCount} optional fields
          </span>
        </div>
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 text-[var(--text-muted)] shrink-0" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-[var(--text-muted)] shrink-0" />
        )}
      </button>

      {expanded && (
        <div className="border-t border-[var(--border-subtle)] px-3.5 py-3 space-y-3">
          {resolvedGroupOrder.map((group) => {
            const fields = schema.filter((field) => field.group === group);
            if (fields.length === 0) {
              return null;
            }

            return (
              <div key={String(group)}>
                <p className="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-muted)] mb-1.5">
                  {groupLabels?.[group] ?? humanizeLabel(String(group))}
                </p>
                <div className="space-y-1">
                  {fields.map((field) => (
                    <div
                      key={field.name}
                      className="flex items-start gap-2 py-1 px-2 rounded text-[12px]"
                    >
                      {field.required ? (
                        <CircleDot className="h-3 w-3 text-[var(--color-info)] shrink-0 mt-0.5" />
                      ) : (
                        <CircleDashed className="h-3 w-3 text-[var(--text-tertiary)] shrink-0 mt-0.5" />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <code
                            className={cn(
                              'font-mono text-[11px] px-1 py-px rounded',
                              field.required
                                ? 'bg-[var(--color-info-light)] text-[var(--color-info)]'
                                : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]',
                            )}
                          >
                            {field.name}
                          </code>
                          {!field.required && (
                            <span className="text-[10px] text-[var(--text-tertiary)] italic">optional</span>
                          )}
                        </div>
                        <p className="text-[11px] text-[var(--text-muted)] mt-0.5">
                          {field.description}
                          <span className="text-[var(--text-tertiary)]"> — e.g. </span>
                          <code className="text-[10px] font-mono text-[var(--text-secondary)]">
                            {field.example || '(empty)'}
                          </code>
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
