import { Select } from '@/components/ui/Select';
import type { MergePolicy, PayloadPolicy } from '@/features/orchestration/types';

interface MergeConfig {
  merge_policy?: MergePolicy;
  payload_policy?: PayloadPolicy;
}

interface Props {
  value: MergeConfig;
  onChange(next: MergeConfig): void;
}

const MERGE_OPTIONS: { value: MergePolicy; label: string; help: string }[] = [
  { value: 'dedupe',      label: 'Dedupe by recipient',  help: 'If the same recipient arrives from multiple branches, emit it once. Payload is resolved by the payload policy below.' },
  { value: 'first_wins',  label: 'First-arriving wins',  help: 'Emit each recipient once, keeping the first branch arrival. Later duplicates are discarded.' },
  { value: 'last_wins',   label: 'Last-arriving wins',   help: 'Emit each recipient once, keeping the last branch arrival. Earlier duplicates are discarded.' },
];

const PAYLOAD_OPTIONS: { value: PayloadPolicy; label: string; help: string }[] = [
  { value: 'first_wins',    label: 'First branch wins',   help: 'The payload from the first branch to arrive is preserved; later arrivals for the same recipient are ignored.' },
  { value: 'last_wins',     label: 'Last branch wins',    help: 'The payload from the last branch to arrive replaces any earlier payload for the same recipient.' },
  { value: 'shallow_merge', label: 'Shallow merge',       help: 'Later arrivals override colliding keys field-by-field; keys absent in the later payload are preserved from earlier ones.' },
];

/**
 * Phase 11 (Commit 2) — `logic.merge` editor.
 *
 * Replaces the legacy ``dedupe: bool`` with explicit recipient-merge and
 * payload-merge policies (Phase 11 §6.5). Both must be set explicitly so
 * "what happens when the same recipient arrives twice" is never undefined.
 */
export function MergePolicyEditor({ value, onChange }: Props) {
  const mp = value.merge_policy ?? 'dedupe';
  const pp = value.payload_policy ?? 'last_wins';
  return (
    <div className="flex flex-col gap-3">
      <Field label="Recipient merge policy">
        <Select
          value={mp}
          onChange={(next) => onChange({ ...value, merge_policy: next as MergePolicy })}
          options={MERGE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
        />
        <p className="mt-1 text-xs text-[var(--text-secondary)]">
          {MERGE_OPTIONS.find((o) => o.value === mp)?.help}
        </p>
      </Field>
      <Field label="Payload merge policy">
        <Select
          value={pp}
          onChange={(next) =>
            onChange({ ...value, payload_policy: next as PayloadPolicy })
          }
          options={PAYLOAD_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
        />
        <p className="mt-1 text-xs text-[var(--text-secondary)]">
          {PAYLOAD_OPTIONS.find((o) => o.value === pp)?.help}
        </p>
      </Field>
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
