import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import type {
  AttemptBackoffKind,
  AttemptPolicy,
} from '@/features/orchestration/types';
import { DEFAULT_ATTEMPT_POLICY } from '@/features/orchestration/types';

import { InspectorInfoButton } from '../inspector/InspectorPrimitives';

interface Props {
  value: AttemptPolicy | undefined;
  onChange(next: AttemptPolicy): void;
}

const BACKOFF_OPTIONS: { value: AttemptBackoffKind; label: string; help: string }[] = [
  { value: 'immediate',   label: 'Immediate',                  help: 'Retry on the same task tick. Best for transient errors.' },
  { value: 'fixed_delay', label: 'Fixed delay (per attempt)',  help: 'Wait `delay_minutes` between attempts. Suspend-based backoff is a follow-up — see backend `attempt_policy.py`.' },
  { value: 'exponential', label: 'Exponential backoff',        help: 'Doubles the delay per retry. Same suspend caveat as fixed_delay.' },
];

/** Per-node attempt-policy sub-form; mirrors the backend `AttemptPolicy` model field-for-field. */
export function AttemptPolicyEditor({ value, onChange }: Props) {
  // Merge stored value with defaults so partial payloads (e.g. legacy node
  // configs missing `retry_on`) don't crash on `.join()` / `.map()`.
  const v: AttemptPolicy = { ...DEFAULT_ATTEMPT_POLICY, ...(value ?? {}) };
  const retryOn = Array.isArray(v.retry_on) ? v.retry_on : [];

  const update = (patch: Partial<AttemptPolicy>) => {
    onChange({ ...v, ...patch });
  };

  return (
    <div className="flex flex-col gap-2 rounded-[var(--radius-default)] border border-[var(--border-default)] p-2">
      <div className="text-[11px] uppercase tracking-wide text-[var(--text-secondary)]">
        Attempt policy
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Max attempts">
          <Input
            type="number"
            min={1}
            max={10}
            value={v.max_attempts}
            onChange={(e) =>
              update({ max_attempts: Math.max(1, Number(e.target.value) || 1) })
            }
          />
        </Field>
        <Field
          label="Backoff"
          info={BACKOFF_OPTIONS.find((o) => o.value === v.backoff_kind)?.help}
        >
          <Select
            value={v.backoff_kind}
            onChange={(next) =>
              update({ backoff_kind: next as AttemptBackoffKind })
            }
            options={BACKOFF_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
          />
        </Field>
      </div>
      {v.backoff_kind !== 'immediate' ? (
        <Field label="Delay (minutes)">
          <Input
            type="number"
            min={0}
            value={v.delay_minutes}
            onChange={(e) => update({ delay_minutes: Number(e.target.value) || 0 })}
          />
        </Field>
      ) : null}
      <Field
        label="Retry on (comma-separated tokens)"
        info={
          <>
            Empty means {'"any classifiable retryable failure"'}. Tokens depend
            on the dispatch node — for HTTP, common values are{' '}
            <code>timeout</code>, <code>http_5xx</code>, <code>transport</code>.
          </>
        }
      >
        <Input
          value={retryOn.join(', ')}
          onChange={(e) =>
            update({
              retry_on: e.target.value
                .split(',')
                .map((s) => s.trim())
                .filter((s) => s.length > 0),
            })
          }
          placeholder="timeout, http_5xx, transport"
        />
      </Field>
    </div>
  );
}

function Field({
  label,
  info,
  children,
}: {
  label: string;
  info?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center gap-1">
        <span className="text-[11px] uppercase tracking-wide text-[var(--text-secondary)]">
          {label}
        </span>
        {info ? (
          <InspectorInfoButton content={info} ariaLabel={`More info about ${label}`} />
        ) : null}
      </div>
      {children}
    </div>
  );
}
