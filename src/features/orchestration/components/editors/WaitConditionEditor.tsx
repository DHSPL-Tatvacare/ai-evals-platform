import { cn } from '@/utils/cn';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { DateTimeField } from '@/components/ui/DateTimeField';
import type { PredicateAst, WaitMode } from '@/features/orchestration/types';

import { PredicateBuilder } from './PredicateBuilder';

type DurationUnit = 'minutes' | 'hours' | 'days';

interface WaitConfig {
  mode?: WaitMode;
  duration_value?: number;
  duration_unit?: DurationUnit;
  /** @deprecated legacy — kept for back-compat; coerced by the backend model_validator */
  duration_hours?: number;
  until_datetime?: string;
  event_name?: string;
  correlation?: Record<string, unknown>;
  event_match?: PredicateAst;
  timeout_hours?: number;
}

const UNIT_OPTIONS: { value: DurationUnit; label: string }[] = [
  { value: 'minutes', label: 'Minutes' },
  { value: 'hours',   label: 'Hours'   },
  { value: 'days',    label: 'Days'    },
];

interface Props {
  value: WaitConfig;
  onChange(next: WaitConfig): void;
}

const MODE_OPTIONS: { value: WaitMode; label: string; help: string }[] = [
  { value: 'duration',         label: 'Wait for duration',          help: 'Wake after N hours. Emits a `wakeup` edge.' },
  { value: 'until_datetime',   label: 'Wait until ISO datetime',    help: 'Wake at a specific UTC time. Emits a `wakeup` edge.' },
  { value: 'event',            label: 'Wait for event',             help: 'Pause here until a matching event arrives, then continue down the Event path.' },
  { value: 'event_or_timeout', label: 'Wait for event OR timeout',  help: 'Whichever happens first. Emits `event` or `timeout`.' },
];

/**
 * Phase 11 (Commit 2) — `logic.wait` editor.
 *
 * Discriminated-union editing: each mode shows only the fields that mode
 * needs. The active mode determines which output edges the validator
 * expects (Phase 11 §6.4).
 */
export function WaitConditionEditor({ value, onChange }: Props) {
  const mode: WaitMode = value.mode ?? 'duration';

  const setMode = (next: WaitMode) => {
    const base: WaitConfig = { mode: next };
    if (next === 'duration') {
      base.duration_value = value.duration_value ?? value.duration_hours ?? 1;
      base.duration_unit = value.duration_unit ?? 'hours';
    }
    if (next === 'until_datetime') base.until_datetime = value.until_datetime ?? '';
    if (next === 'event' || next === 'event_or_timeout') {
      base.event_name = value.event_name ?? '';
      base.correlation = value.correlation ?? {};
      base.event_match = value.event_match;
    }
    if (next === 'event_or_timeout') {
      base.timeout_hours = value.timeout_hours ?? 24;
    }
    onChange(base);
  };

  return (
    <div className="flex flex-col gap-3">
      <Field label="Mode">
        <Select
          value={mode}
          onChange={(next) => setMode(next as WaitMode)}
          options={MODE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
        />
        <p className="mt-1 text-xs text-[var(--text-secondary)]">
          {MODE_OPTIONS.find((o) => o.value === mode)?.help}
        </p>
      </Field>

      {mode === 'duration' ? (
        <Field label="Duration">
          <div className={cn('flex gap-2')}>
            <Input
              type="number"
              min={0}
              className="flex-1"
              value={value.duration_value ?? value.duration_hours ?? ''}
              onChange={(e) =>
                onChange({
                  ...value,
                  duration_value: Number(e.target.value),
                  duration_unit: value.duration_unit ?? 'hours',
                })
              }
              placeholder="amount"
            />
            <div className="w-32">
              <Select
                value={value.duration_unit ?? 'hours'}
                onChange={(next) =>
                  onChange({
                    ...value,
                    duration_unit: next as DurationUnit,
                    duration_value: value.duration_value ?? value.duration_hours ?? 1,
                  })
                }
                options={UNIT_OPTIONS}
              />
            </div>
          </div>
        </Field>
      ) : null}

      {mode === 'until_datetime' ? (
        <Field label="Wake at (UTC ISO datetime)">
          <DateTimeField
            value={value.until_datetime ?? ''}
            onChange={(next) => onChange({ ...value, until_datetime: next })}
          />
        </Field>
      ) : null}

      {mode === 'event' || mode === 'event_or_timeout' ? (
        <>
          <p className="text-xs text-[var(--text-secondary)]">
            Today this resumes on a WhatsApp reply; full event matching is coming soon.
          </p>
          <Field label="Event name">
            <Input
              type="text"
              value={value.event_name ?? ''}
              onChange={(e) => onChange({ ...value, event_name: e.target.value })}
              placeholder="wati.message_replied"
            />
            <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
              The event that resumes this step — e.g. a WhatsApp reply or a CRM stage change.
            </p>
          </Field>
          <Field label="Event match (optional predicate)">
            <p className="mb-1 text-xs text-[var(--text-secondary)]">
              Optional — only resume when the event&apos;s data matches these conditions. Leave empty to resume on any matching event.
            </p>
            <PredicateBuilder
              value={value.event_match}
              onChange={(next) => onChange({ ...value, event_match: next })}
            />
          </Field>
        </>
      ) : null}

      {mode === 'event_or_timeout' ? (
        <Field label="Timeout (hours)">
          <Input
            type="number"
            min={0}
            value={value.timeout_hours ?? ''}
            onChange={(e) =>
              onChange({
                ...value,
                timeout_hours: Number(e.target.value),
              })
            }
            placeholder="hours before timeout fires"
          />
        </Field>
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
