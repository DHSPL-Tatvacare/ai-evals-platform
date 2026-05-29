/** Date + time picker that emits a UTC ISO string (no milliseconds). */
import { useEffect, useState } from 'react';
import { Calendar as CalendarIcon } from 'lucide-react';
import { format, isSameDay } from 'date-fns';
import { cn } from '@/utils/cn';
import { Popover, PopoverTrigger, PopoverContent } from './Popover';
import { Calendar } from './Calendar';
import { Select } from './Select';
import type { SelectOption } from './Select';

export interface DateTimeFieldProps {
  /** UTC ISO string like `2026-05-01T14:30:00Z`, or `''` for unset. */
  value: string;
  onChange: (next: string) => void;
  min?: Date | null;
  max?: Date | null;
  placeholder?: string;
  className?: string;
}

// Generate 00–23 hour options.
const HOUR_OPTIONS: SelectOption[] = Array.from({ length: 24 }, (_, i) => ({
  value: String(i).padStart(2, '0'),
  label: String(i).padStart(2, '0'),
}));

// Generate 00–55 minute options in steps of 5.
const MINUTE_OPTIONS: SelectOption[] = Array.from({ length: 12 }, (_, i) => ({
  value: String(i * 5).padStart(2, '0'),
  label: String(i * 5).padStart(2, '0'),
}));

const TZ_NAME = Intl.DateTimeFormat().resolvedOptions().timeZone;

/** Round a minute up to the nearest 5-minute grid step (capped at 55). */
function ceilToStep(minute: number): number {
  return Math.min(Math.ceil(minute / 5) * 5, 55);
}

/** Parse a UTC ISO string into a local Date, or null if empty/invalid. */
function parseUtcToLocal(utcIso: string): Date | null {
  if (!utcIso) return null;
  const d = new Date(utcIso);
  return isNaN(d.getTime()) ? null : d;
}

/** Combine a local calendar date + local hour + local minute into a UTC ISO string. */
function buildUtcIso(localDate: Date, localHour: string, localMinute: string): string {
  const d = new Date(
    localDate.getFullYear(),
    localDate.getMonth(),
    localDate.getDate(),
    parseInt(localHour, 10),
    parseInt(localMinute, 10),
    0,
  );
  // Strip milliseconds: 2026-05-01T14:30:00.000Z → 2026-05-01T14:30:00Z
  return d.toISOString().replace(/\.\d{3}Z$/, 'Z');
}

const TRIGGER_BASE =
  'flex w-full items-center gap-2 rounded-[var(--radius-default)] border border-[var(--border-default)] bg-[var(--bg-primary)] px-2.5 py-1.5 text-[13px] text-[var(--text-primary)] focus:border-[var(--border-focus)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-accent)]/50';

export function DateTimeField({
  value,
  onChange,
  min,
  max,
  placeholder = 'Select date & time',
  className,
}: DateTimeFieldProps) {
  const [open, setOpen] = useState(false);

  const localDate = parseUtcToLocal(value);

  // Derive current local hour/minute from the incoming UTC value.
  const localHour = localDate ? String(localDate.getHours()).padStart(2, '0') : '00';
  const localMinute = localDate
    ? String(Math.round(localDate.getMinutes() / 5) * 5)
        .padStart(2, '0')
        .replace('60', '55')
    : '00';

  // When a future-only `min` is set and the selected date is min's calendar
  // day, the hour/minute lists are clamped so an earlier time on today is not
  // pickable. Other days keep the full grid (min already gates the date).
  const minOnSelectedDay = min && localDate ? isSameDay(localDate, min) : false;
  const minHour = min ? min.getHours() : 0;
  const minMinuteStep = min ? ceilToStep(min.getMinutes()) : 0;

  const hourOptions = minOnSelectedDay
    ? HOUR_OPTIONS.filter((o) => parseInt(o.value, 10) >= minHour)
    : HOUR_OPTIONS;

  const minuteOptions =
    minOnSelectedDay && parseInt(localHour, 10) === minHour
      ? MINUTE_OPTIONS.filter((o) => parseInt(o.value, 10) >= minMinuteStep)
      : MINUTE_OPTIONS;

  // Clamp an incoming value that sits before `min` forward to `min`, so a stale
  // or typed past instant can never be persisted from this future-only field.
  // Guard against the SAME seconds-zeroed/rounded target the clamp produces, so
  // a `min` with seconds>0 cannot re-fire onChange every render (render storm).
  useEffect(() => {
    if (!min || !localDate) return;
    const target = buildUtcIso(
      min,
      String(minHour).padStart(2, '0'),
      String(minMinuteStep).padStart(2, '0'),
    );
    if (localDate.getTime() >= new Date(target).getTime()) return;
    onChange(target);
    // localDate is derived from value; depending on value covers it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, min]);

  const triggerLabel = localDate
    ? format(localDate, 'dd MMM yyyy, HH:mm')
    : null;

  function handleDateSelect(date: Date) {
    // When a date is selected, preserve existing or default time.
    onChange(buildUtcIso(date, localHour, localMinute));
  }

  function handleHourChange(hour: string) {
    if (!localDate) return;
    onChange(buildUtcIso(localDate, hour, localMinute));
  }

  function handleMinuteChange(minute: string) {
    if (!localDate) return;
    onChange(buildUtcIso(localDate, localHour, minute));
  }

  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button type="button" className={TRIGGER_BASE}>
            <CalendarIcon className="h-3.5 w-3.5 shrink-0 text-[var(--text-muted)]" />
            <span className={cn('flex-1 truncate text-left', !triggerLabel && 'text-[var(--text-muted)]')}>
              {triggerLabel ?? placeholder}
            </span>
            {/* Show the browser timezone so the user knows what tz they're picking in. */}
            <span className="ml-auto shrink-0 text-[11px] text-[var(--text-muted)]">
              {TZ_NAME}
            </span>
          </button>
        </PopoverTrigger>

        <PopoverContent align="start" className="p-0">
          <div className="flex flex-col">
            <Calendar
              value={localDate}
              min={min}
              max={max}
              onSelect={handleDateSelect}
            />

            {/* Time row — only meaningful once a date is chosen. */}
            <div className="flex items-center gap-2 border-t border-[var(--border-default)] px-3 py-2">
              <span className="text-[12px] text-[var(--text-muted)]">Time</span>
              <Select
                size="sm"
                className="w-[72px]"
                value={localHour}
                onChange={handleHourChange}
                options={hourOptions}
                placeholder="HH"
                side="top"
              />
              <span className="text-[var(--text-muted)]">:</span>
              <Select
                size="sm"
                className="w-[72px]"
                value={localMinute}
                onChange={handleMinuteChange}
                options={minuteOptions}
                placeholder="MM"
                side="top"
              />
            </div>
          </div>
        </PopoverContent>
      </Popover>

      {/* UTC caption — shown only when a value is set. */}
      {value && (
        <p className="text-[11px] text-[var(--text-muted)]">
          Stored as <span className="font-mono">{value}</span> (UTC)
        </p>
      )}
    </div>
  );
}
