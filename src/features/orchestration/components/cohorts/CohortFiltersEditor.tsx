import { Plus, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { Combobox } from '@/components/ui/Combobox';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { COHORT_FILTER_OPS } from '@/features/orchestration/contracts/nodeConfig';
import { useCohortColumnValues } from '@/features/orchestration/queries/cohorts';
import type { CohortColumnType } from '@/features/orchestration/types';
import type { CohortFilter } from '@/services/api/orchestrationCohorts';

// ─── Datatype matrix ─────────────────────────────────────────────────────────

type CohortFilterOp = (typeof COHORT_FILTER_OPS)[number];

const OPS_FOR_TYPE: Record<CohortColumnType, CohortFilterOp[]> = {
  string: ['eq', 'neq', 'in', 'not_in', 'contains'],
  integer: ['eq', 'neq', 'gt', 'gte', 'lt', 'lte'],
  number: ['eq', 'neq', 'gt', 'gte', 'lt', 'lte'],
  datetime: ['eq', 'neq', 'gt', 'gte', 'lt', 'lte'],
  boolean: ['eq', 'neq'],
};

const LIST_OPS: ReadonlySet<string> = new Set(['in', 'not_in']);

function isListOp(op: string): boolean {
  return LIST_OPS.has(op);
}

function coerceValue(op: string, raw: string): unknown {
  if (isListOp(op)) {
    return raw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
  }
  if (op === 'gte' || op === 'gt' || op === 'lte' || op === 'lt') {
    const n = Number(raw);
    return Number.isFinite(n) ? n : raw;
  }
  return raw;
}

function valueToInputString(value: unknown): string {
  if (Array.isArray(value)) return value.map(String).join(', ');
  if (value == null) return '';
  return String(value);
}

// Keep an already-selected value visible even when it's outside the fetched
// page (high-cardinality columns only return the first N distinct values).
function withSelected(
  options: { value: string; label: string }[],
  selected: string[],
): { value: string; label: string }[] {
  const present = new Set(options.map((o) => o.value));
  const extra = selected.filter((s) => s && !present.has(s)).map((s) => ({ value: s, label: s }));
  return extra.length ? [...extra, ...options] : options;
}

// ─── Per-row child component — allows hooks at top level ────────────────────

interface FilterRowProps {
  filter: CohortFilter;
  index: number;
  disabled?: boolean;
  /** When present, column is a dropdown over these names. */
  columnOptions?: string[];
  /** When present (inline mode), drives operator narrowing + smart value control. */
  columnTypes?: Record<string, CohortColumnType>;
  sourceRef?: string;
  onUpdate: (index: number, patch: Partial<CohortFilter>) => void;
  onRemove: (index: number) => void;
}

function FilterRow({
  filter: f,
  index: idx,
  disabled,
  columnOptions,
  columnTypes,
  sourceRef,
  onUpdate,
  onRemove,
}: FilterRowProps) {
  // Resolve type; fall back to 'string' when descriptor is absent.
  const colType: CohortColumnType = columnTypes ? (columnTypes[f.column] ?? 'string') : 'string';
  // Whether we are in datatype-aware mode (SourceCohortPicker provides both).
  const isTyped = Boolean(columnTypes && sourceRef);

  // Operator options — narrowed when typed, full list when legacy (CohortDetailPane).
  const opOptions = isTyped
    ? (OPS_FOR_TYPE[colType] ?? COHORT_FILTER_OPS).map((op) => ({ value: op, label: op }))
    : COHORT_FILTER_OPS.map((op) => ({ value: op, label: op }));

  // Column options for the column picker (keeps out-of-list current column selectable).
  function columnSelectOptions(current: string) {
    const names = Array.from(
      new Set([...(current ? [current] : []), ...(columnOptions ?? [])]),
    );
    return names.map((c) => ({ value: c, label: c }));
  }

  function handleColumnChange(col: string) {
    if (!isTyped) {
      onUpdate(idx, { column: col });
      return;
    }
    const newType: CohortColumnType = columnTypes?.[col] ?? 'string';
    const validOps = OPS_FOR_TYPE[newType] ?? COHORT_FILTER_OPS;
    const currentOpValid = validOps.includes(f.op as CohortFilterOp);
    onUpdate(idx, {
      column: col,
      op: currentOpValid ? f.op : (validOps[0] as CohortFilter['op']),
      value: currentOpValid ? f.value : '',
    });
  }

  function handleOpChange(op: string) {
    onUpdate(idx, {
      op: op as CohortFilter['op'],
      // Reset value when switching list↔scalar so stale shape doesn't fail server.
      value: isListOp(op) === isListOp(f.op) ? f.value : isListOp(op) ? [] : '',
    });
  }

  // Async combobox for string column values — only fires when isTyped + column set.
  const { options: asyncOptions, loading: asyncLoading, onSearchChange } = useCohortColumnValues(
    isTyped && colType === 'string' ? sourceRef : null,
    isTyped && colType === 'string' && f.column ? f.column : null,
  );

  // ─── Value control rendering ─────────────────────────────────────────────

  function renderValueControl() {
    if (!isTyped) {
      // Legacy fallback: free-text input (CohortDetailPane, etc.)
      return (
        <Input
          value={valueToInputString(f.value)}
          onChange={(e) => onUpdate(idx, { value: coerceValue(f.op, e.target.value) })}
          placeholder={isListOp(f.op) ? 'comma, separated, values' : 'value'}
          disabled={disabled}
          className="min-w-0 flex-1"
        />
      );
    }

    if (colType === 'boolean') {
      return (
        <Select
          value={f.value === true ? 'true' : f.value === false ? 'false' : ''}
          onChange={(v) => onUpdate(idx, { value: v === 'true' })}
          options={[
            { value: 'true', label: 'true' },
            { value: 'false', label: 'false' },
          ]}
          placeholder="value"
          disabled={disabled}
        />
      );
    }

    if (colType === 'integer' || colType === 'number') {
      return (
        <Input
          type="number"
          value={valueToInputString(f.value)}
          onChange={(e) => {
            const n = Number(e.target.value);
            onUpdate(idx, { value: e.target.value === '' ? '' : Number.isFinite(n) ? n : e.target.value });
          }}
          placeholder="value"
          disabled={disabled}
          className="min-w-0 flex-1"
        />
      );
    }

    if (colType === 'datetime') {
      return (
        <Input
          type="date"
          value={valueToInputString(f.value)}
          onChange={(e) => onUpdate(idx, { value: e.target.value })}
          disabled={disabled}
          className="min-w-0 flex-1"
        />
      );
    }

    // string type
    if (f.op === 'contains') {
      return (
        <Input
          value={valueToInputString(f.value)}
          onChange={(e) => onUpdate(idx, { value: e.target.value })}
          placeholder="text to match"
          disabled={disabled}
          className="min-w-0 flex-1"
        />
      );
    }

    if (isListOp(f.op)) {
      // multi combobox — value is string[]
      const currentValues = Array.isArray(f.value) ? f.value.map(String) : [];
      return (
        <div className="min-w-0 flex-1">
          <Combobox
            multi
            value={currentValues}
            onChange={(vals) => onUpdate(idx, { value: vals })}
            options={withSelected(asyncOptions, currentValues)}
            onSearchChange={onSearchChange}
            loading={asyncLoading}
            placeholder="select values…"
            disabled={disabled}
          />
        </div>
      );
    }

    // eq / neq — single combobox
    const currentVal = typeof f.value === 'string' ? f.value : valueToInputString(f.value);
    return (
      <div className="min-w-0 flex-1">
        <Combobox
          value={currentVal}
          onChange={(v) => onUpdate(idx, { value: v })}
          options={withSelected(asyncOptions, currentVal ? [currentVal] : [])}
          onSearchChange={onSearchChange}
          loading={asyncLoading}
          placeholder="select a value…"
          disabled={disabled}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-2">
      <div className="flex items-center gap-2">
        {columnOptions ? (
          <div className="min-w-0 flex-1">
            <Select
              value={f.column}
              onChange={handleColumnChange}
              options={columnSelectOptions(f.column)}
              placeholder={columnOptions.length === 0 ? 'select fields first' : 'column'}
              disabled={disabled}
            />
          </div>
        ) : (
          <Input
            value={f.column}
            onChange={(e) => onUpdate(idx, { column: e.target.value })}
            placeholder="column"
            disabled={disabled}
            className="min-w-0 flex-1"
          />
        )}
        <button
          type="button"
          onClick={() => onRemove(idx)}
          disabled={disabled}
          aria-label="Remove filter"
          className="shrink-0 rounded-md p-1 text-[var(--text-muted)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--color-error)] disabled:opacity-50"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="flex items-center gap-2">
        <div className="w-24 shrink-0">
          <Select
            value={f.op}
            onChange={handleOpChange}
            options={opOptions}
          />
        </div>
        {renderValueControl()}
      </div>
    </div>
  );
}

// ─── Editor ──────────────────────────────────────────────────────────────────

interface Props {
  value: CohortFilter[];
  onChange: (next: CohortFilter[]) => void;
  disabled?: boolean;
  /** When provided, the column becomes a picker over these names instead of free text. */
  columnOptions?: string[];
  /** Column name→type map derived from the source's schemaDescriptor. */
  columnTypes?: Record<string, CohortColumnType>;
  /** Source reference passed to the column-values endpoint. */
  sourceRef?: string;
}

export function CohortFiltersEditor({ value, onChange, disabled, columnOptions, columnTypes, sourceRef }: Props) {
  function updateFilter(index: number, patch: Partial<CohortFilter>) {
    const next = [...value];
    next[index] = { ...next[index], ...patch };
    onChange(next);
  }

  function removeFilter(index: number) {
    onChange(value.filter((_, i) => i !== index));
  }

  function addFilter() {
    onChange([...value, { column: '', op: 'eq', value: '' }]);
  }

  return (
    <div className="flex flex-col gap-2">
      {value.length === 0 ? (
        <p className="text-[12px] text-[var(--text-muted)]">
          No filters yet. Add one to narrow the audience.
        </p>
      ) : null}
      {value.map((f, idx) => (
        <FilterRow
          key={idx}
          filter={f}
          index={idx}
          disabled={disabled}
          columnOptions={columnOptions}
          columnTypes={columnTypes}
          sourceRef={sourceRef}
          onUpdate={updateFilter}
          onRemove={removeFilter}
        />
      ))}
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={addFilter}
        disabled={disabled}
        className="self-start gap-1.5"
      >
        <Plus className="h-3.5 w-3.5" aria-hidden /> Add filter
      </Button>
    </div>
  );
}
