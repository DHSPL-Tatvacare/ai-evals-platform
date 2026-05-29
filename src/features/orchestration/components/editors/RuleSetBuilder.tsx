import { useMemo } from 'react';
import { Plus, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { Combobox } from '@/components/ui/Combobox';
import { Input } from '@/components/ui/Input';
import { useFieldSpotlight } from '@/features/orchestration/components/inspector/fieldSpotlight';
import { InspectorField } from '@/features/orchestration/components/inspector/InspectorPrimitives';
import {
  formatStringListInputValue,
  isListOperator,
  parseStringListInputValue,
  PREDICATE_OPERATOR_OPTIONS,
  predicateOperatorNeedsValue,
} from '@/features/orchestration/components/editors/operatorContracts';
import type { UpstreamOutcomeEnum } from '@/services/api/orchestration';
import type {
  AndPredicate,
  LeafPredicate,
  OrPredicate,
  PredicateAst,
  PredicateOp,
} from '@/features/orchestration/types';
import { cn } from '@/utils';

type Combinator = 'all' | 'any';

// Canonical outcome step-field keys the engine actually writes as a
// dispatch outcome. Voice writes `voice_outcome`
// (upstream_variables._DISPATCH_EMITS["voice.place_call"]); messaging writes
// reply fields (wa_button_id / wa_reply_text), NOT a canonical outcome — so a
// messaging producer contributes outcome enums but no entry here. A producer's
// outcome path is dropdown-eligible only if the engine declares it upstream.
const OUTCOME_FIELD_KEYS = new Set<string>(['voice_outcome']);

/** A rule is either a single leaf condition or a one-level nested group. */
type Rule = LeafPredicate | AndPredicate | OrPredicate;

interface Props {
  value: PredicateAst | undefined;
  onChange(next: PredicateAst): void;
  /** Optional payload field names — surfaces a Combobox. When empty the
   *  field input is plain text so authors can reference any key. */
  fieldOptions?: string[];
  /** Upstream dispatch outcomes — when present the leaf VALUE is a dropdown of
   *  canonical outcomes (canonical as the label, provider raw label as muted
   *  right-aligned meta). Stores the canonical value; the provider label is
   *  display-only context. */
  outcomeOptions?: UpstreamOutcomeEnum[];
  /** When false (default for nested groups), the "add nested group" action
   *  is hidden so nesting is capped at one level. */
  allowNesting?: boolean;
}

function emptyLeaf(): LeafPredicate {
  return { field: '', op: 'eq', value: '' };
}

function isLeaf(p: PredicateAst): p is LeafPredicate {
  return !('and' in p) && !('or' in p) && !('not' in p);
}

/** Decompose any predicate into a (combinator, rules[]) view. A bare leaf
 *  becomes ALL with a single rule; NOT and deeper trees are surfaced as a
 *  single rule so the editor never silently drops them. */
function toRuleSet(value: PredicateAst | undefined): {
  combinator: Combinator;
  rules: Rule[];
} {
  if (!value) return { combinator: 'all', rules: [emptyLeaf()] };
  if ('and' in value) return { combinator: 'all', rules: value.and as Rule[] };
  if ('or' in value) return { combinator: 'any', rules: value.or as Rule[] };
  return { combinator: 'all', rules: [value as Rule] };
}

function fromRuleSet(combinator: Combinator, rules: Rule[]): PredicateAst {
  if (rules.length === 1 && combinator === 'all') return rules[0];
  return combinator === 'all'
    ? ({ and: rules } as AndPredicate)
    : ({ or: rules } as OrPredicate);
}

const COMBINATOR_OPTIONS: { value: Combinator; label: string }[] = [
  { value: 'all', label: 'ALL' },
  { value: 'any', label: 'ANY' },
];

/**
 * Shared rule-set editor: "Match [ALL|ANY] of these rules". Each rule stacks
 * Field / Operator / Value on its own row (no 3-column squish). Used by the
 * eligibility filter and by every branch of the conditional router. Maps
 * ALL → `and`, ANY → `or`; mirrors the backend predicate contract.
 */
export function RuleSetBuilder({
  value,
  onChange,
  fieldOptions,
  outcomeOptions,
  allowNesting = true,
}: Props) {
  const { combinator, rules } = useMemo(() => toRuleSet(value), [value]);

  const emit = (nextCombinator: Combinator, nextRules: Rule[]) => {
    onChange(fromRuleSet(nextCombinator, nextRules));
  };

  const setCombinator = (next: Combinator) => emit(next, rules);
  const updateRule = (idx: number, next: Rule) =>
    emit(combinator, rules.map((r, i) => (i === idx ? next : r)));
  const removeRule = (idx: number) => {
    const next = rules.filter((_, i) => i !== idx);
    emit(combinator, next.length > 0 ? next : [emptyLeaf()]);
  };
  const addRule = () => emit(combinator, [...rules, emptyLeaf()]);
  const addGroup = () =>
    emit(combinator, [...rules, { and: [emptyLeaf()] } as AndPredicate]);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
        <span>Match</span>
        <div className="flex overflow-hidden rounded-[var(--radius-default)] border border-[var(--border-default)]">
          {COMBINATOR_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setCombinator(opt.value)}
              aria-pressed={combinator === opt.value}
              className={cn(
                'px-2 py-0.5 text-xs font-medium transition-colors',
                combinator === opt.value
                  ? 'bg-[var(--bg-brand-soft)] text-[var(--text-brand)]'
                  : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]',
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <span>of these rules</span>
      </div>

      {rules.map((rule, idx) => (
        <div
          key={idx}
          className="flex flex-col gap-2 rounded-[var(--radius-default)] border border-[var(--border-default)] bg-[var(--bg-tertiary)] p-2"
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
              {combinator === 'all' ? 'AND' : 'OR'}
            </span>
            <button
              type="button"
              onClick={() => removeRule(idx)}
              className="text-[var(--text-muted)] hover:text-[var(--color-error)]"
              aria-label={`Remove rule ${idx + 1}`}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
          {isLeaf(rule) ? (
            <LeafRow
              value={rule}
              onChange={(next) => updateRule(idx, next)}
              fieldOptions={fieldOptions}
              outcomeOptions={outcomeOptions}
            />
          ) : (
            <RuleSetBuilder
              value={rule}
              onChange={(next) => updateRule(idx, next as Rule)}
              fieldOptions={fieldOptions}
              outcomeOptions={outcomeOptions}
              allowNesting={false}
            />
          )}
        </div>
      ))}

      <div className="flex gap-2">
        <Button variant="secondary" size="sm" onClick={addRule}>
          <Plus className="mr-1 h-3.5 w-3.5" />
          Add rule
        </Button>
        {allowNesting ? (
          <Button variant="ghost" size="sm" onClick={addGroup}>
            <Plus className="mr-1 h-3.5 w-3.5" />
            Add group
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function LeafRow({
  value,
  onChange,
  fieldOptions,
  outcomeOptions,
}: {
  value: LeafPredicate;
  onChange(next: LeafPredicate): void;
  fieldOptions?: string[];
  outcomeOptions?: UpstreamOutcomeEnum[];
}) {
  const spotlight = useFieldSpotlight();
  // Canonical outcome value options: the canonical is the clear label; the
  // provider's raw label rides in `meta` (muted, right-aligned) so any provider
  // surfaces the same way without baking the name into the label. Stores
  // canonical; the current value stays selectable so a hand-set value isn't dropped.
  const valueOptions = useMemo(() => {
    const byCanonical = new Map<string, { value: string; label: string; meta?: string }>();
    for (const o of outcomeOptions ?? []) {
      if (!byCanonical.has(o.canonical)) {
        byCanonical.set(o.canonical, {
          value: o.canonical,
          label: o.canonical,
          meta: o.providerLabel,
        });
      }
    }
    const current = typeof value.value === 'string' ? value.value : '';
    if (current && !byCanonical.has(current)) {
      byCanonical.set(current, { value: current, label: current });
    }
    return Array.from(byCanonical.values());
  }, [outcomeOptions, value.value]);
  // A leaf is outcome-bearing only when its field is a producer's canonical
  // outcome path — `steps.<sourceNodeId>.<key>` where the producer is present
  // in outcomeOptions AND `<key>` is a canonical-outcome field the engine
  // writes (OUTCOME_FIELD_KEYS). This is producer-general: a messaging producer
  // surfaces outcome enums but writes no canonical outcome field, so its phantom
  // `steps.<wa>.voice_outcome` never qualifies. When upstream declares the step
  // fields (fieldOptions), the path must also be engine-declared, so a producer
  // can only ever expose the outcome field the runtime actually populates.
  const outcomeFieldPaths = useMemo(() => {
    const declared = new Set(fieldOptions ?? []);
    const paths = new Set<string>();
    for (const o of outcomeOptions ?? []) {
      for (const key of OUTCOME_FIELD_KEYS) {
        const path = `steps.${o.sourceNodeId}.${key}`;
        if ((fieldOptions?.length ?? 0) === 0 || declared.has(path)) {
          paths.add(path);
        }
      }
    }
    return paths;
  }, [outcomeOptions, fieldOptions]);
  const useOutcomeDropdown =
    (outcomeOptions?.length ?? 0) > 0 &&
    !isListOperator(value.op) &&
    outcomeFieldPaths.has(value.field);
  // Always offer the current field as an option so a hand-typed key isn't
  // dropped when upstream suggestions don't include it.
  const options = useMemo(() => {
    const set = new Set(fieldOptions ?? []);
    if (value.field) set.add(value.field);
    return Array.from(set);
  }, [fieldOptions, value.field]);

  return (
    <div className="flex flex-col gap-2">
      <InspectorField label="Field" className="gap-1">
        {fieldOptions && fieldOptions.length > 0 ? (
          <Combobox
            size="sm"
            value={value.field}
            onChange={(next) => onChange({ ...value, field: next })}
            options={options.map((f) => ({ value: f, label: f }))}
            placeholder="payload field"
            {...spotlight}
          />
        ) : (
          <Input
            value={value.field}
            onChange={(e) => onChange({ ...value, field: e.target.value })}
            placeholder="payload field"
          />
        )}
      </InspectorField>
      <InspectorField label="Operator" className="gap-1">
        <Combobox
          size="sm"
          value={value.op}
          onChange={(next) => onChange({ ...value, op: next as PredicateOp })}
          options={PREDICATE_OPERATOR_OPTIONS.map((o) => ({
            value: o.value,
            label: o.label,
          }))}
        />
      </InspectorField>
      <InspectorField label="Value" className="gap-1">
        {predicateOperatorNeedsValue(value.op) ? (
          useOutcomeDropdown ? (
            <Combobox
              size="sm"
              value={typeof value.value === 'string' ? value.value : ''}
              onChange={(next) => onChange({ ...value, value: next })}
              options={valueOptions}
              placeholder="Select an outcome"
            />
          ) : isListOperator(value.op) ? (
            <ListValueInput
              value={value.value}
              onChange={(next) => onChange({ ...value, value: next })}
            />
          ) : (
            <Input
              value={
                value.value === undefined || value.value === null
                  ? ''
                  : Array.isArray(value.value)
                    ? String(value.value[0] ?? '')
                    : String(value.value)
              }
              onChange={(e) => onChange({ ...value, value: e.target.value })}
              placeholder="value"
            />
          )
        ) : (
          <span className="text-xs text-[var(--text-muted)]">
            (no value needed)
          </span>
        )}
      </InspectorField>
    </div>
  );
}

function ListValueInput({
  value,
  onChange,
}: {
  value: unknown;
  onChange(next: string[]): void;
}) {
  const initialValue = formatStringListInputValue(value);
  return (
    <Input
      key={initialValue}
      type="text"
      defaultValue={initialValue}
      onChange={(e) => onChange(parseStringListInputValue(e.target.value))}
      placeholder="a, b, c"
    />
  );
}
