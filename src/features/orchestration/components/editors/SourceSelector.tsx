import { useCallback, useMemo, useState } from 'react';

import { Combobox } from '@/components/ui/Combobox';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { DatasetSourcePicker } from '@/features/orchestration/components/datasets/DatasetSourcePicker';
import type {
  CohortColumnType,
  CohortSource,
  WorkflowType,
} from '@/features/orchestration/types';
import { cn } from '@/utils';

interface CohortQueryConfig {
  source_ref?: string;
  filters?: CohortFilter[];
  payload_fields?: string[];
  lookback_hours?: number | null;
  lookback_column?: string;
  consent_gate_channel?: string;
  // legacy fields tolerated on read; never written by this editor
  source_table?: string;
  id_column?: string;
  payload_columns?: string[];
}

interface CohortFilter {
  column?: string;
  op?: string;
  value?: unknown;
}

interface SourceColumn {
  name: string;
  type: CohortColumnType;
}

const TYPE_LABELS: Record<CohortColumnType, string> = {
  integer: 'number',
  number: 'number',
  boolean: 'boolean',
  datetime: 'datetime',
  string: 'text',
};

const OP_OPTIONS_BY_TYPE: Record<CohortColumnType, Array<{ value: string; label: string }>> = {
  integer: [
    { value: 'gte', label: '>=' },
    { value: 'gt', label: '>' },
    { value: 'lte', label: '<=' },
    { value: 'lt', label: '<' },
    { value: 'eq', label: '=' },
    { value: 'neq', label: '!=' },
  ],
  number: [
    { value: 'gte', label: '>=' },
    { value: 'gt', label: '>' },
    { value: 'lte', label: '<=' },
    { value: 'lt', label: '<' },
    { value: 'eq', label: '=' },
    { value: 'neq', label: '!=' },
  ],
  boolean: [
    { value: 'eq', label: '=' },
    { value: 'neq', label: '!=' },
  ],
  datetime: [
    { value: 'gte', label: 'on/after' },
    { value: 'gt', label: 'after' },
    { value: 'lte', label: 'on/before' },
    { value: 'lt', label: 'before' },
    { value: 'eq', label: '=' },
    { value: 'neq', label: '!=' },
  ],
  string: [
    { value: 'eq', label: '=' },
    { value: 'neq', label: '!=' },
    { value: 'contains', label: 'contains' },
  ],
};

interface Props {
  workflowType: WorkflowType;
  appId: string;
  value: CohortQueryConfig;
  onChange(next: CohortQueryConfig): void;
}

/**
 * Phase 11 (Commit 2) — `source.cohort_query` editor.
 *
 * Authors pick a registered cohort source by ``source_ref``; the editor
 * surfaces the catalog-defined allowed payload columns, allowed filter
 * columns, and allowed lookback columns so authors never have to know the
 * underlying table name. Source-specific routing config (legacy
 * ``next_node_id``) does not appear here — the visual graph determines
 * the successor (Phase 11 §6.1).
 */
export function SourceSelector({ workflowType, appId, value, onChange }: Props) {
  // The picker owns the source-catalog fetch; we only need the *selected*
  // entry here so the payload-field / lookback-column UI can hydrate from
  // the entry's allowed-column lists. Stash whatever the picker hands
  // back when the operator switches sources.
  const [selected, setSelected] = useState<CohortSource | null>(null);

  const filterColumns = useMemo<SourceColumn[]>(() => {
    if (!selected) return [];
    const descriptorColumns = selected.schemaDescriptor?.columns ?? [];
    if (descriptorColumns.length > 0) {
      return descriptorColumns
        .filter((c) => selected.allowedFilterColumns.includes(c.name))
        .map((c) => ({ name: c.name, type: c.type }));
    }
    return selected.allowedFilterColumns.map((name) => ({ name, type: 'string' }));
  }, [selected]);

  const setSourceRef = (next: string, entry: CohortSource) => {
    setSelected(entry);
    // Switching sources clears filters / payload selections — column sets
    // diverge between the static catalog and dataset entries, and silently
    // retaining columns the new source can't project would create a
    // definition that fails validation at publish time. (v1: clear and
    // let the operator reselect; migrating column-by-column is a follow-up.)
    onChange({
      ...value,
      source_ref: next,
      payload_fields: [],
      filters: [],
      lookback_column: entry.allowedLookbackColumns.includes(
        value.lookback_column ?? '',
      )
        ? value.lookback_column
        : undefined,
    });
  };

  const togglePayloadField = (col: string) => {
    const current = new Set(value.payload_fields ?? []);
    if (current.has(col)) current.delete(col);
    else current.add(col);
    onChange({ ...value, payload_fields: Array.from(current) });
  };

  // When the picker's catalog fetch resolves, look up the saved
  // ``source_ref`` so the payload-field / lookback-column UI can hydrate
  // without the operator re-clicking the dropdown.
  const handleSourcesLoaded = useCallback(
    (sources: CohortSource[]) => {
      const ref = value.source_ref;
      if (!ref) return;
      const match = sources.find((s) => s.sourceRef === ref) ?? null;
      setSelected((prev) => (prev?.sourceRef === match?.sourceRef ? prev : match));
    },
    [value.source_ref],
  );

  return (
    <div className="flex flex-col gap-3">
      <Field label="Source">
        <DatasetSourcePicker
          appId={appId}
          workflowType={workflowType}
          value={value.source_ref ?? null}
          onChange={setSourceRef}
          onSourcesLoaded={handleSourcesLoaded}
        />
      </Field>

      {selected ? (
        <>
          <Field label="Payload fields">
            <p className="mb-1 text-[11px] text-[var(--text-secondary)]">
              Recipient payload exposed to downstream nodes. Engineering-owned —
              tenants cannot project arbitrary columns.
            </p>
            <div className="flex flex-wrap gap-1.5">
              {selected.allowedPayloadColumns.map((col) => {
                const active = (value.payload_fields ?? []).includes(col);
                return (
                  <button
                    key={col}
                    type="button"
                    onClick={() => togglePayloadField(col)}
                    className={cn(
                      'rounded-[var(--radius-default)] border px-2 py-0.5 text-xs',
                      active
                        ? 'border-[var(--color-brand)] bg-[var(--bg-brand-soft)] text-[var(--text-brand)]'
                        : 'border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]',
                    )}
                  >
                    {col}
                  </button>
                );
              })}
            </div>
          </Field>

          <Field label="Filters">
            <FilterEditor
              columns={filterColumns}
              value={value.filters ?? []}
              onChange={(filters) => onChange({ ...value, filters })}
            />
          </Field>

          <Field label="Lookback (hours)">
            <Input
              type="number"
              min={0}
              value={value.lookback_hours ?? ''}
              onChange={(e) =>
                onChange({
                  ...value,
                  lookback_hours:
                    e.target.value === '' ? null : Number(e.target.value),
                })
              }
              placeholder="optional — leave blank for no lookback"
            />
          </Field>

          {selected.allowedLookbackColumns.length > 0 ? (
            <Field label="Lookback column">
              <Combobox
                value={value.lookback_column ?? ''}
                onChange={(next) =>
                  onChange({ ...value, lookback_column: next })
                }
                options={selected.allowedLookbackColumns.map((c) => ({
                  value: c,
                  label: c,
                }))}
                placeholder="Pick a timestamp column"
              />
            </Field>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-sm font-medium text-[var(--text-primary)]">
        {label}
      </span>
      {children}
    </div>
  );
}

function FilterEditor({
  columns,
  value,
  onChange,
}: {
  columns: SourceColumn[];
  value: CohortFilter[];
  onChange(next: CohortFilter[]): void;
}) {
  const byName = useMemo(
    () => new Map(columns.map((c) => [c.name, c])),
    [columns],
  );

  const makeDefaultFilter = (): CohortFilter | null => {
    const first = columns[0];
    if (!first) return null;
    return {
      column: first.name,
      op: defaultOp(first.type),
      value: defaultValue(first.type),
    };
  };

  const addFilter = () => {
    const next = makeDefaultFilter();
    if (next) onChange([...value, next]);
  };

  const updateAt = (idx: number, patch: Partial<CohortFilter>) => {
    onChange(value.map((f, i) => (i === idx ? { ...f, ...patch } : f)));
  };

  const removeAt = (idx: number) => {
    onChange(value.filter((_, i) => i !== idx));
  };

  return (
    <div className="flex flex-col gap-2">
      {value.length === 0 ? (
        <p className="text-xs text-[var(--text-secondary)]">
          No filters. The workflow starts with every row in the selected source.
        </p>
      ) : null}
      {value.map((filter, idx) => {
        const column = byName.get(filter.column ?? '') ?? columns[0];
        const type = column?.type ?? 'string';
        return (
          <div
            key={idx}
            className="grid grid-cols-[minmax(0,1.2fr)_96px_minmax(0,1fr)_auto] items-center gap-2"
          >
            <Select
              value={filter.column ?? ''}
              onChange={(columnName) => {
                const nextColumn = byName.get(columnName);
                const nextType = nextColumn?.type ?? 'string';
                updateAt(idx, {
                  column: columnName,
                  op: defaultOp(nextType),
                  value: defaultValue(nextType),
                });
              }}
              options={columns.map((c) => ({
                value: c.name,
                label: `${c.name} (${TYPE_LABELS[c.type]})`,
              }))}
              placeholder="Column"
              size="sm"
            />
            <Select
              value={filter.op ?? defaultOp(type)}
              onChange={(op) => updateAt(idx, { op })}
              options={OP_OPTIONS_BY_TYPE[type]}
              placeholder="Op"
              size="sm"
            />
            <FilterValueInput
              type={type}
              value={filter.value}
              onChange={(nextValue) => updateAt(idx, { value: nextValue })}
            />
            <button
              type="button"
              onClick={() => removeAt(idx)}
              className={cn(
                'rounded-[var(--radius-default)] border border-[var(--border-default)]',
                'px-2 py-1 text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]',
              )}
            >
              Remove
            </button>
          </div>
        );
      })}
      <div>
        <button
          type="button"
          onClick={addFilter}
          disabled={columns.length === 0}
          className={cn(
            'rounded-[var(--radius-default)] border border-[var(--border-default)]',
            'px-2.5 py-1 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]',
            'disabled:cursor-not-allowed disabled:opacity-50',
          )}
        >
          Add filter
        </button>
      </div>
    </div>
  );
}

function FilterValueInput({
  type,
  value,
  onChange,
}: {
  type: CohortColumnType;
  value: unknown;
  onChange(next: unknown): void;
}) {
  if (type === 'boolean') {
    return (
      <Select
        value={value === false ? 'false' : 'true'}
        onChange={(next) => onChange(next === 'true')}
        options={[
          { value: 'true', label: 'true' },
          { value: 'false', label: 'false' },
        ]}
        size="sm"
      />
    );
  }
  const inputType = type === 'integer' || type === 'number' ? 'number' : 'text';
  return (
    <Input
      type={inputType}
      value={value === null || value === undefined ? '' : String(value)}
      onChange={(e) => {
        if (type === 'integer' || type === 'number') {
          onChange(e.target.value === '' ? null : Number(e.target.value));
          return;
        }
        onChange(e.target.value);
      }}
      placeholder={type === 'datetime' ? '2026-05-01T00:00:00Z' : 'Value'}
    />
  );
}

function defaultOp(type: CohortColumnType): string {
  if (type === 'integer' || type === 'number' || type === 'datetime') return 'gte';
  return 'eq';
}

function defaultValue(type: CohortColumnType): unknown {
  if (type === 'integer' || type === 'number') return 0;
  if (type === 'boolean') return true;
  return '';
}
