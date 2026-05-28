import { cn } from '@/utils/cn';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { DateTimeField } from '@/components/ui/DateTimeField';
import type { PredicateAst, WaitMode } from '@/features/orchestration/types';

import { PredicateBuilder } from './PredicateBuilder';

type DurationUnit = 'minutes' | 'hours' | 'days';

// Modes offered in the dropdown — pure 'event' is no longer selectable.
type SelectableMode = Exclude<WaitMode, 'event'>;

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

const MODE_OPTIONS: { value: SelectableMode; label: string; help: string }[] = [
  {
    value: 'duration',
    label: 'Wait for a set time',
    help: 'Pause here, then continue after the time you set.',
  },
  {
    value: 'until_datetime',
    label: 'Wait until a specific date & time',
    help: 'Pause here until the date and time you choose (UTC).',
  },
  {
    value: 'event_or_timeout',
    label: 'Wait for an event (with a time limit)',
    help: 'Pause until the event arrives, or continue down the timeout path once the time limit passes.',
  },
];

/**
 * `logic.wait` editor.
 *
 * Discriminated-union editing: each mode shows only the fields that mode
 * needs. Pure `event` mode is no longer offered (backend rejects publish);
 * legacy definitions with `mode==='event'` are steered to `event_or_timeout`
 * in the display layer without silently mutating stored config.
 */
export function WaitConditionEditor({ value, onChange }: Props) {
  // Map legacy pure-event to event_or_timeout for the display layer only.
  const displayMode: SelectableMode =
    value.mode === 'event' || value.mode === 'event_or_timeout'
      ? 'event_or_timeout'
      : (value.mode ?? 'duration');

  const setMode = (next: SelectableMode) => {
    const base: WaitConfig = { mode: next };
    if (next === 'duration') {
      base.duration_value = value.duration_value ?? value.duration_hours ?? 1;
      base.duration_unit = value.duration_unit ?? 'hours';
    }
    if (next === 'until_datetime') base.until_datetime = value.until_datetime ?? '';
    if (next === 'event_or_timeout') {
      base.event_name = value.event_name ?? '';
      base.correlation = {
        recipient_id_field: 'recipient_id',
        ...value.correlation,
      };
      base.event_match = value.event_match;
      base.timeout_hours = value.timeout_hours ?? 24;
    }
    onChange(base);
  };

  // For event modes, ensure a default timeout is visible even on legacy pure-event defs
  // so the author can save without blanking out the field (no silent mutation on open).
  const isEventMode = displayMode === 'event_or_timeout';

  return (
    <div className="flex flex-col gap-3">
      <Field label="Mode">
        <Select
          value={displayMode}
          onChange={(next) => setMode(next as SelectableMode)}
          options={MODE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
        />
        <p className="mt-1 text-xs text-[var(--text-secondary)]">
          {MODE_OPTIONS.find((o) => o.value === displayMode)?.help}
        </p>
      </Field>

      {displayMode === 'duration' ? (
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

      {displayMode === 'until_datetime' ? (
        <Field label="Wake at (UTC ISO datetime)">
          <DateTimeField
            value={value.until_datetime ?? ''}
            onChange={(next) => onChange({ ...value, until_datetime: next })}
          />
        </Field>
      ) : null}

      {isEventMode ? (
        <>
          <Field label="Event to wait for">
            <Input
              type="text"
              value={value.event_name ?? ''}
              onChange={(e) => onChange({ ...value, event_name: e.target.value })}
              placeholder="voice.completed"
            />
            <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
              The event that resumes this step — e.g. a call finishing or a CRM update.
            </p>
          </Field>
          <Field label="Match the contact by">
            <Input
              type="text"
              value={
                typeof value.correlation?.recipient_id_field === 'string'
                  ? value.correlation.recipient_id_field
                  : ''
              }
              onChange={(e) =>
                onChange({
                  ...value,
                  correlation: {
                    ...value.correlation,
                    recipient_id_field: e.target.value,
                  },
                })
              }
              placeholder="recipient_id"
            />
            <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
              The event field that identifies the contact (defaults to the contact id).
            </p>
          </Field>
          <Field label="Only resume if… (optional)">
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

      {isEventMode ? (
        <Field label="Time limit (hours)">
          <Input
            type="number"
            min={0}
            // For legacy pure-event defs opened without a timeout, default to 24 in the input
            // so the field isn't blank — without writing back until the author changes it.
            value={value.timeout_hours ?? 24}
            onChange={(e) =>
              onChange({
                ...value,
                timeout_hours: Number(e.target.value),
              })
            }
            placeholder="hours before giving up"
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
