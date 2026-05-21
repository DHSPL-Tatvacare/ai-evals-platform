import { useMemo } from 'react';
import { AlertCircle, CheckCircle2, Plus, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { Combobox } from '@/components/ui/Combobox';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { cn } from '@/utils/cn';
import type {
  SplitBranch,
  SplitMode,
} from '@/features/orchestration/types';

interface SplitConfig {
  mode?: SplitMode;
  field?: string;
  branches?: SplitBranch[];
  default_branch_id?: string;
  drop_unmatched?: boolean;
  holdout_percent?: number;
}

interface Props {
  value: SplitConfig;
  onChange(next: SplitConfig): void;
  /** Payload fields available for the ``by_field`` mode. */
  fieldOptions?: string[];
}

const MODE_OPTIONS: { value: SplitMode; label: string; help: string }[] = [
  { value: 'by_field',    label: 'By field value',    help: 'Match a payload field against per-branch values' },
  { value: 'random',      label: 'Random allocation', help: 'Weighted random pick across branches' },
  { value: 'percentage',  label: 'Percentage split',  help: 'Assign a fixed percentage to each branch — totals must equal 100%' },
];

let _branchIdCounter = 0;
function makeBranchId(label: string): string {
  const slug = label.replace(/[^a-zA-Z0-9_]+/g, '_').replace(/^_+|_+$/g, '') || 'branch';
  _branchIdCounter += 1;
  return `${slug}_${_branchIdCounter}`;
}

export function SplitBranchEditor({ value, onChange, fieldOptions }: Props) {
  const mode: SplitMode = value.mode ?? 'by_field';
  const branches = useMemo(() => value.branches ?? [], [value.branches]);

  const setMode = (next: SplitMode) => {
    onChange({ ...value, mode: next });
  };

  const updateBranch = (idx: number, patch: Partial<SplitBranch>) => {
    onChange({
      ...value,
      branches: branches.map((b, i) => (i === idx ? { ...b, ...patch } : b)),
    });
  };

  const removeBranch = (idx: number) => {
    const removed = branches[idx];
    const next = branches.filter((_, i) => i !== idx);
    onChange({
      ...value,
      branches: next,
      default_branch_id:
        value.default_branch_id === removed.id ? undefined : value.default_branch_id,
    });
  };

  const addBranch = () => {
    const label = `Branch ${branches.length + 1}`;
    const newBranch: SplitBranch = { id: makeBranchId(label), label };
    if (mode === 'by_field') newBranch.match = '';
    if (mode === 'random') newBranch.weight = 1;
    if (mode === 'percentage') newBranch.percent = 0;
    onChange({ ...value, branches: [...branches, newBranch] });
  };

  // Percentage total validator
  const branchTotal = mode === 'percentage'
    ? branches.reduce((acc, b) => acc + (b.percent ?? 0), 0)
    : 0;
  const holdout = mode === 'percentage' ? (value.holdout_percent ?? 0) : 0;
  const percentTotal = branchTotal + holdout;
  const percentValid = mode !== 'percentage' || percentTotal === 100;

  const defaultOptions = branches.map((b) => ({ value: b.id, label: b.label }));

  return (
    <div className="flex flex-col gap-3">
      <Field label="Mode">
        <Select
          value={mode}
          onChange={(next) => setMode(next as SplitMode)}
          options={MODE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
        />
        <p className="mt-1 text-xs text-[var(--text-secondary)]">
          {MODE_OPTIONS.find((o) => o.value === mode)?.help}
        </p>
      </Field>

      {mode === 'by_field' ? (
        <Field label="Split field">
          {fieldOptions && fieldOptions.length > 0 ? (
            <Combobox
              value={value.field ?? ''}
              onChange={(next) => onChange({ ...value, field: next })}
              options={fieldOptions.map((f) => ({ value: f, label: f }))}
              placeholder="payload field"
            />
          ) : (
            <Input
              value={value.field ?? ''}
              onChange={(e) => onChange({ ...value, field: e.target.value })}
              placeholder="payload field"
            />
          )}
        </Field>
      ) : null}

      <Field label="Branches">
        <div className="flex flex-col gap-2">
          {branches.length === 0 ? (
            <p className="text-xs text-[var(--text-secondary)]">
              No branches — click Add to create one.
            </p>
          ) : null}
          {branches.map((b, idx) => (
            <div
              key={b.id}
              className="rounded-[var(--radius-default)] bg-[var(--bg-tertiary)] p-2"
            >
              <div className="mb-2 flex items-center gap-2">
                <Input
                  className="flex-1"
                  value={b.label}
                  onChange={(e) => updateBranch(idx, { label: e.target.value })}
                  placeholder="branch label"
                />
                <button
                  type="button"
                  onClick={() => removeBranch(idx)}
                  className="text-[var(--text-muted)] hover:text-[var(--color-error)]"
                  aria-label={`Remove branch ${b.label}`}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
              {mode === 'by_field' ? (
                <Input
                  value={
                    typeof b.match === 'string'
                      ? b.match
                      : b.match === undefined || b.match === null
                        ? ''
                        : String(b.match)
                  }
                  onChange={(e) => updateBranch(idx, { match: e.target.value })}
                  placeholder="match value"
                />
              ) : null}
              {mode === 'random' ? (
                <Input
                  type="number"
                  min={0}
                  value={b.weight ?? 1}
                  onChange={(e) =>
                    updateBranch(idx, { weight: Number(e.target.value) })
                  }
                  placeholder="weight"
                />
              ) : null}
              {mode === 'percentage' ? (
                <div className="flex items-center gap-1.5">
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    value={b.percent ?? 0}
                    onChange={(e) =>
                      updateBranch(idx, { percent: Number(e.target.value) })
                    }
                    placeholder="0"
                    className="w-20 text-right"
                  />
                  <span className="text-xs text-[var(--text-secondary)]">%</span>
                </div>
              ) : null}
            </div>
          ))}
          <Button variant="secondary" size="sm" onClick={addBranch}>
            <Plus className="mr-1 h-3.5 w-3.5" />
            Add branch
          </Button>
        </div>
      </Field>

      {mode === 'percentage' ? (
        <>
          <HoldoutToggle
            holdout={holdout}
            onChange={(next) =>
              onChange({ ...value, holdout_percent: next > 0 ? next : undefined })
            }
          />
          <PercentTotal total={percentTotal} valid={percentValid} />
        </>
      ) : null}

      {mode !== 'percentage' ? (
        <Field label="Default branch (unmatched)">
          <Combobox
            value={value.default_branch_id ?? ''}
            onChange={(next) => onChange({ ...value, default_branch_id: next })}
            options={defaultOptions}
            placeholder="(none — drops unmatched recipients)"
          />
          <label className="mt-1 flex items-center gap-2 text-xs text-[var(--text-secondary)]">
            <input
              type="checkbox"
              checked={Boolean(value.drop_unmatched)}
              onChange={(e) =>
                onChange({ ...value, drop_unmatched: e.target.checked })
              }
            />
            Drop recipients that match no branch (instead of the default)
          </label>
        </Field>
      ) : null}
    </div>
  );
}

// ─── sub-components ────────────────────────────────────────────────────────

interface HoldoutToggleProps {
  holdout: number;
  onChange(next: number): void;
}

function HoldoutToggle({ holdout, onChange }: HoldoutToggleProps) {
  const enabled = holdout > 0;
  return (
    <Field label="Control holdout">
      <label className="flex items-center gap-2 text-sm text-[var(--text-primary)]">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => onChange(e.target.checked ? 10 : 0)}
          className="h-4 w-4 rounded border-[var(--border-default)] accent-[var(--color-primary)]"
        />
        Reserve a holdout branch (routes to a <em>control</em> edge — no further steps)
      </label>
      {enabled ? (
        <div className="mt-2 flex items-center gap-1.5">
          <Input
            type="number"
            min={1}
            max={99}
            value={holdout}
            onChange={(e) => onChange(Number(e.target.value))}
            placeholder="10"
            className="w-20 text-right"
          />
          <span className="text-xs text-[var(--text-secondary)]">% holdout</span>
        </div>
      ) : null}
      <p className="mt-1 text-xs text-[var(--text-secondary)]">
        Recipients routed to the holdout exit the flow immediately and receive no further messages.
      </p>
    </Field>
  );
}

interface PercentTotalProps {
  total: number;
  valid: boolean;
}

function PercentTotal({ total, valid }: PercentTotalProps) {
  return (
    <div
      className={cn(
        'flex items-center gap-1.5 rounded-[var(--radius-default)] px-2 py-1.5 text-sm font-medium',
        valid
          ? 'bg-[var(--color-success-subtle)] text-[var(--color-success)]'
          : 'bg-[var(--color-warning-subtle)] text-[var(--color-warning)]',
      )}
    >
      {valid ? (
        <CheckCircle2 className="h-4 w-4 shrink-0" />
      ) : (
        <AlertCircle className="h-4 w-4 shrink-0" />
      )}
      <span>
        Total: {total}%
        {!valid ? ` — must equal 100% (${total < 100 ? `${100 - total}% unallocated` : `${total - 100}% over`})` : ''}
      </span>
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
