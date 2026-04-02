import { useMemo } from 'react';
import { AlertTriangle, ArrowRight, CheckCircle2 } from 'lucide-react';

import { cn } from '@/utils';

import type { ColumnMapping, CsvFieldDef } from '../types';

interface CsvFieldMapperProps {
  csvHeaders: string[];
  schema: CsvFieldDef[];
  mapping: ColumnMapping;
  onMappingChange: (mapping: ColumnMapping) => void;
  missingFields: string[];
}

export function CsvFieldMapper({
  csvHeaders,
  schema,
  mapping,
  onMappingChange,
  missingFields,
}: CsvFieldMapperProps) {
  const usedSources = useMemo(() => {
    const used = new Set<string>();
    for (const [, source] of mapping) {
      used.add(source.toLowerCase());
    }
    return used;
  }, [mapping]);

  const allMapped = missingFields.every((field) => mapping.has(field));
  const requiredSet = useMemo(
    () => new Set(schema.filter((field) => field.required).map((field) => field.name)),
    [schema],
  );

  const handleFieldMap = (targetField: string, sourceColumn: string) => {
    const next = new Map(mapping);
    if (!sourceColumn) {
      next.delete(targetField);
    } else {
      next.set(targetField, sourceColumn);
    }
    onMappingChange(next);
  };

  return (
    <div className="space-y-2.5">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-3.5 w-3.5 text-[var(--color-warning)]" />
        <span className="text-[12px] font-medium text-[var(--text-primary)]">
          {missingFields.length} required {missingFields.length === 1 ? 'column' : 'columns'} not found
        </span>
        {allMapped && (
          <span className="inline-flex items-center gap-1 text-[11px] text-[var(--color-success)]">
            <CheckCircle2 className="h-3 w-3" />
            All mapped
          </span>
        )}
      </div>
      <p className="text-[11px] text-[var(--text-muted)]">
        Map your CSV columns to the expected fields below. Only required missing columns are shown.
      </p>

      <div className="space-y-1.5">
        {missingFields.map((targetField) => {
          const fieldDef = schema.find((field) => field.name === targetField);
          const currentSource = mapping.get(targetField) ?? '';
          const isRequired = requiredSet.has(targetField);
          const isMapped = currentSource !== '';

          return (
            <div
              key={targetField}
              className={cn(
                'flex items-center gap-2 px-3 py-2 rounded-md border transition-colors',
                isMapped
                  ? 'border-[var(--border-success)] bg-[var(--surface-success)]'
                  : 'border-[var(--border-default)] bg-[var(--bg-secondary)]/50',
              )}
            >
              <div className="flex-1 min-w-0">
                <code
                  className={cn(
                    'font-mono text-[11px] px-1 py-px rounded',
                    isRequired
                      ? 'bg-[var(--color-info-light)] text-[var(--color-info)]'
                      : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]',
                  )}
                >
                  {targetField}
                </code>
                {fieldDef && (
                  <span className="ml-1.5 text-[10px] text-[var(--text-muted)]">{fieldDef.description}</span>
                )}
              </div>

              <ArrowRight className="h-3 w-3 text-[var(--text-tertiary)] shrink-0" />

              <select
                value={currentSource}
                onChange={(e) => handleFieldMap(targetField, e.target.value)}
                className={cn(
                  'w-44 shrink-0 px-2 py-1 text-[11px] font-mono rounded border bg-[var(--bg-primary)] text-[var(--text-primary)]',
                  'focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-accent)]',
                  isMapped ? 'border-[var(--border-success)]' : 'border-[var(--border-default)]',
                )}
              >
                <option value="">— select column —</option>
                {csvHeaders.map((column) => {
                  const isUsed = usedSources.has(column.toLowerCase()) && currentSource.toLowerCase() !== column.toLowerCase();
                  return (
                    <option key={column} value={column} disabled={isUsed}>
                      {column}{isUsed ? ' (used)' : ''}
                    </option>
                  );
                })}
              </select>
            </div>
          );
        })}
      </div>
    </div>
  );
}
