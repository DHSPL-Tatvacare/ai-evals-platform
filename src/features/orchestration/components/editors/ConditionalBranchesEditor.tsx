import { useMemo } from 'react';
import { Plus, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import {
  InspectorEmptyState,
  InspectorField,
} from '@/features/orchestration/components/inspector/InspectorPrimitives';
import { RuleSetBuilder } from '@/features/orchestration/components/editors/RuleSetBuilder';
import type {
  ConditionalBranch,
  PredicateAst,
} from '@/features/orchestration/types';

interface ConditionalConfig {
  branches?: ConditionalBranch[];
}

interface Props {
  value: ConditionalConfig;
  onChange(next: ConditionalConfig): void;
  /** Payload fields available at this node, walked from upstream nodes. */
  fieldOptions?: string[];
}

let _branchIdCounter = 0;
function makeBranchId(label: string): string {
  const slug =
    label.replace(/[^a-zA-Z0-9_]+/g, '_').replace(/^_+|_+$/g, '') || 'branch';
  _branchIdCounter += 1;
  return `${slug}_${_branchIdCounter}`;
}

function emptyPredicate(): PredicateAst {
  return { field: '', op: 'eq', value: '' };
}

/**
 * `logic.conditional` editor — an N-way criteria router. Each branch carries
 * a stable routing id (the output-edge id), an editable display name, and its
 * own rule set. Branches evaluate top-to-bottom; the first match wins and
 * unmatched contacts fall to the always-present `default` branch. This is
 * criteria routing — distinct from Segment Split's percentage allocation.
 */
export function ConditionalBranchesEditor({
  value,
  onChange,
  fieldOptions,
}: Props) {
  const branches = useMemo(() => value.branches ?? [], [value.branches]);

  const updateBranch = (idx: number, patch: Partial<ConditionalBranch>) =>
    onChange({
      ...value,
      branches: branches.map((b, i) => (i === idx ? { ...b, ...patch } : b)),
    });
  const removeBranch = (idx: number) =>
    onChange({ ...value, branches: branches.filter((_, i) => i !== idx) });
  const addBranch = () => {
    const label = `Branch ${branches.length + 1}`;
    const next: ConditionalBranch = {
      id: makeBranchId(label),
      label,
      predicate: emptyPredicate(),
    };
    onChange({ ...value, branches: [...branches, next] });
  };

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-[var(--text-secondary)]">
        Each contact takes the first branch whose rules match. Contacts that
        match no branch continue on the default branch.
      </p>

      {branches.length === 0 ? (
        <InspectorEmptyState>
          No branches yet. Add a branch to route contacts by criteria.
        </InspectorEmptyState>
      ) : null}

      {branches.map((branch, idx) => (
        <div
          key={branch.id}
          className="flex flex-col gap-2 rounded-[var(--radius-default)] border border-[var(--border-default)] bg-[var(--bg-primary)] p-3"
        >
          <div className="flex items-center gap-2">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--bg-tertiary)] text-[11px] font-medium text-[var(--text-secondary)]">
              {idx + 1}
            </span>
            <Input
              className="flex-1"
              value={branch.label}
              onChange={(e) => updateBranch(idx, { label: e.target.value })}
              placeholder="Branch name"
            />
            <button
              type="button"
              onClick={() => removeBranch(idx)}
              className="text-[var(--text-muted)] hover:text-[var(--color-error)]"
              aria-label={`Remove branch ${branch.label}`}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
            <span>Routes to output</span>
            <code className="rounded-[var(--radius-default)] bg-[var(--bg-elevated)] px-1.5 py-0.5 text-[var(--text-primary)]">
              {branch.id}
            </code>
          </div>
          <InspectorField label="Rules" className="gap-1.5">
            <RuleSetBuilder
              value={branch.predicate}
              onChange={(next) => updateBranch(idx, { predicate: next })}
              fieldOptions={fieldOptions}
            />
          </InspectorField>
        </div>
      ))}

      <div className="flex items-center gap-1.5 rounded-[var(--radius-default)] border border-dashed border-[var(--border-default)] bg-[var(--bg-tertiary)] px-3 py-2 text-xs text-[var(--text-secondary)]">
        <span>Unmatched contacts continue on</span>
        <code className="rounded-[var(--radius-default)] bg-[var(--bg-elevated)] px-1.5 py-0.5 text-[var(--text-primary)]">
          default
        </code>
      </div>

      <Button variant="secondary" size="sm" onClick={addBranch}>
        <Plus className="mr-1 h-3.5 w-3.5" />
        Add branch
      </Button>
    </div>
  );
}
