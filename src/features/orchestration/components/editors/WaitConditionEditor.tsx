import { Combobox } from '@/components/ui/Combobox';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { DateTimeField } from '@/components/ui/DateTimeField';
import { DurationField, type DurationUnit } from '@/components/ui/DurationField';
import type { UpstreamEvent } from '@/services/api/orchestration';
import type { PredicateAst, WaitMode } from '@/features/orchestration/types';

import { PredicateBuilder } from './PredicateBuilder';

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

interface Props {
  value: WaitConfig;
  onChange(next: WaitConfig): void;
  /** Resumable events surfaced by upstream dispatch producers. When present
   *  the event-name field is a dropdown (no free-text). */
  eventOptions?: UpstreamEvent[];
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
export function WaitConditionEditor({ value, onChange, eventOptions }: Props) {
  // Map legacy pure-event to event_or_timeout for the display layer only.
  const displayMode: SelectableMode =
    value.mode === 'event' || value.mode === 'event_or_timeout'
      ? 'event_or_timeout'
      : (value.mode ?? 'duration');

  // Emit only the fields valid for `mode`, carrying forward existing values.
  // Stripping stale keys (e.g. a blank `until_datetime` left by a prior mode)
  // is what keeps publish unblocked — no orphaned field reaches the backend.
  const emitForMode = (mode: SelectableMode, overrides: Partial<WaitConfig>) => {
    const merged = { ...value, ...overrides };
    const base: WaitConfig = { mode };
    if (mode === 'duration') {
      base.duration_value = merged.duration_value ?? merged.duration_hours ?? 1;
      base.duration_unit = merged.duration_unit ?? 'hours';
    }
    if (mode === 'until_datetime') base.until_datetime = merged.until_datetime ?? '';
    if (mode === 'event_or_timeout') {
      base.event_name = merged.event_name ?? '';
      base.correlation = {
        recipient_id_field: 'recipient_id',
        ...merged.correlation,
      };
      base.event_match = merged.event_match;
      base.timeout_hours = merged.timeout_hours ?? 24;
    }
    onChange(base);
  };

  const setMode = (next: SelectableMode) => emitForMode(next, {});

  // For event modes, ensure a default timeout is visible even on legacy pure-event defs
  // so the author can save without blanking out the field (no silent mutation on open).
  const isEventMode = displayMode === 'event_or_timeout';

  // Dedupe events by name (multiple producers may emit the same one); show the
  // provider as muted context. The stored value is always selectable, so a
  // legacy hand-set event_name isn't dropped if upstream no longer lists it.
  const eventNameOptions = (() => {
    const byName = new Map<string, { value: string; label: string; meta?: string }>();
    for (const e of eventOptions ?? []) {
      if (!byName.has(e.eventName)) {
        byName.set(e.eventName, { value: e.eventName, label: e.eventName, meta: e.provider });
      }
    }
    const current = value.event_name ?? '';
    if (current && !byName.has(current)) {
      byName.set(current, { value: current, label: current });
    }
    return Array.from(byName.values());
  })();

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
          <DurationField
            mode="value-unit"
            value={value.duration_value ?? value.duration_hours ?? null}
            unit={value.duration_unit ?? 'hours'}
            onChange={(nextValue, nextUnit) =>
              emitForMode('duration', {
                duration_value: nextValue,
                duration_unit: nextUnit,
              })
            }
          />
        </Field>
      ) : null}

      {displayMode === 'until_datetime' ? (
        <Field label="Wake at (UTC ISO datetime)">
          <DateTimeField
            value={value.until_datetime ?? ''}
            min={new Date()}
            onChange={(next) => emitForMode('until_datetime', { until_datetime: next })}
          />
        </Field>
      ) : null}

      {isEventMode ? (
        <>
          <Field label="Event to wait for">
            <Combobox
              value={value.event_name ?? ''}
              onChange={(next) => emitForMode('event_or_timeout', { event_name: next })}
              options={eventNameOptions}
              placeholder="Select an event"
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
                emitForMode('event_or_timeout', {
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
              onChange={(next) => emitForMode('event_or_timeout', { event_match: next })}
            />
          </Field>
        </>
      ) : null}

      {isEventMode ? (
        <Field label="Time limit">
          <DurationField
            mode="hours"
            // For legacy pure-event defs opened without a timeout, default to 24 in the input
            // so the field isn't blank — without writing back until the author changes it.
            hours={value.timeout_hours ?? 24}
            minHours={1}
            onChange={(nextHours) =>
              emitForMode('event_or_timeout', { timeout_hours: nextHours })
            }
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
