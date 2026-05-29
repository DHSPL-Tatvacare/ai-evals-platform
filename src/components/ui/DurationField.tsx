import { Input } from './Input';
import { Select } from './Select';
import { cn } from '@/utils/cn';

export type DurationUnit = 'minutes' | 'hours' | 'days';

const UNIT_OPTIONS: { value: DurationUnit; label: string }[] = [
  { value: 'minutes', label: 'Minutes' },
  { value: 'hours', label: 'Hours' },
  { value: 'days', label: 'Days' },
];

const UNIT_SECONDS: Record<DurationUnit, number> = {
  minutes: 60,
  hours: 3600,
  days: 86400,
};

// Largest unit that divides `seconds` evenly, so 259200 surfaces as "3 days"
// rather than "72 hours". Falls back to minutes for sub-hour / non-aligned values.
function decompose(seconds: number): { value: number; unit: DurationUnit } {
  for (const unit of ['days', 'hours', 'minutes'] as DurationUnit[]) {
    const size = UNIT_SECONDS[unit];
    if (seconds % size === 0) return { value: seconds / size, unit };
  }
  return { value: Math.round(seconds / UNIT_SECONDS.minutes), unit: 'minutes' };
}

interface ValueUnitProps {
  mode: 'value-unit';
  value: number | null;
  unit: DurationUnit;
  onChange: (value: number, unit: DurationUnit) => void;
  className?: string;
}

interface SecondsProps {
  mode: 'seconds';
  /** Canonical stored value — an int number of seconds. */
  seconds: number | null;
  /** Emits the recomposed int number of seconds; the stored contract is unchanged. */
  onChange: (seconds: number) => void;
  /** Optional contract floor — emitted seconds are clamped up to this minimum. */
  minSeconds?: number;
  className?: string;
}

interface HoursProps {
  mode: 'hours';
  /** Canonical stored value — an int number of hours (e.g. wait timeout_hours). */
  hours: number | null;
  /** Emits the recomposed int number of hours; the stored contract is unchanged. */
  onChange: (hours: number) => void;
  /** Optional contract floor — emitted hours are clamped up to this minimum. */
  minHours?: number;
  className?: string;
}

type DurationFieldProps = ValueUnitProps | SecondsProps | HoursProps;

/**
 * Shared value+unit duration control. Three modes:
 * - `value-unit` stores the raw amount + unit (wait node duration).
 * - `seconds` displays friendly units but stores an int number of seconds
 *   (e.g. webhook_ttl_seconds 259200 ↔ "3 days"), so the config contract holds.
 * - `hours` displays friendly units but stores an int number of hours
 *   (e.g. wait timeout_hours 24 ↔ "1 day"), so the config contract holds.
 */
export function DurationField(props: DurationFieldProps) {
  if (props.mode === 'hours') {
    const canonical = props.hours != null ? props.hours * UNIT_SECONDS.hours : null;
    const { value, unit } =
      canonical != null && canonical > 0
        ? decompose(canonical)
        : { value: null as number | null, unit: 'hours' as DurationUnit };
    const floor = props.minHours ?? 0;
    const toHours = (seconds: number) =>
      Math.max(Math.round(seconds / UNIT_SECONDS.hours), floor);
    return (
      <Row
        value={value}
        unit={unit}
        className={props.className}
        onValue={(next) => props.onChange(toHours(next * UNIT_SECONDS[unit]))}
        onUnit={(nextUnit) => props.onChange(toHours((value ?? 0) * UNIT_SECONDS[nextUnit]))}
      />
    );
  }
  if (props.mode === 'seconds') {
    const { value, unit } =
      props.seconds != null && props.seconds > 0
        ? decompose(props.seconds)
        : { value: null as number | null, unit: 'days' as DurationUnit };
    const floor = props.minSeconds ?? 0;
    const clamp = (seconds: number) => Math.max(seconds, floor);
    return (
      <Row
        value={value}
        unit={unit}
        className={props.className}
        onValue={(next) => props.onChange(clamp(next * UNIT_SECONDS[unit]))}
        onUnit={(nextUnit) => props.onChange(clamp((value ?? 0) * UNIT_SECONDS[nextUnit]))}
      />
    );
  }
  return (
    <Row
      value={props.value}
      unit={props.unit}
      className={props.className}
      onValue={(next) => props.onChange(next, props.unit)}
      onUnit={(nextUnit) => props.onChange(props.value ?? 0, nextUnit)}
    />
  );
}

interface RowProps {
  value: number | null;
  unit: DurationUnit;
  onValue: (value: number) => void;
  onUnit: (unit: DurationUnit) => void;
  className?: string;
}

function Row({ value, unit, onValue, onUnit, className }: RowProps) {
  return (
    <div className={cn('flex gap-2', className)}>
      <Input
        type="number"
        min={0}
        className="flex-1"
        value={value ?? ''}
        onChange={(e) => {
          if (e.target.value === '') return;
          const parsed = Number(e.target.value);
          if (!Number.isFinite(parsed)) return;
          onValue(parsed);
        }}
        placeholder="amount"
      />
      <div className="w-32">
        <Select
          value={unit}
          onChange={(next) => onUnit(next as DurationUnit)}
          options={UNIT_OPTIONS}
        />
      </div>
    </div>
  );
}
