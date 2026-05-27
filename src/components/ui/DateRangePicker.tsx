import { useState } from 'react';
import { Calendar as CalendarIcon, ChevronLeft, ChevronRight } from 'lucide-react';
import {
  format,
  parseISO,
  isValid,
  startOfMonth,
  endOfMonth,
  startOfWeek,
  endOfWeek,
  eachDayOfInterval,
  addMonths,
  subMonths,
  isSameDay,
  isSameMonth,
  isToday,
  isAfter,
  isBefore,
} from 'date-fns';
import { cn } from '@/utils/cn';
import { Popover, PopoverTrigger, PopoverContent } from './Popover';

const WEEKDAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'] as const;

export interface DateRangePreset {
  id: string;
  label: string;
}

export interface DateRangePickerProps {
  presets: DateRangePreset[];
  /** Preset id when a preset is active, else null. */
  activePreset: string | null;
  /** 'YYYY-MM-DD' when a custom range is active. */
  from: string | null;
  to: string | null;
  onPresetSelect: (id: string) => void;
  /** Fires once both endpoints are chosen. */
  onCustomRange: (from: string, to: string) => void;
  className?: string;
}

const TRIGGER_CLASS =
  'flex items-center gap-2 rounded-[var(--radius-default)] border border-[var(--border-default)] bg-[var(--bg-primary)] px-2.5 py-1.5 text-[13px] text-[var(--text-primary)] hover:bg-[var(--bg-secondary)] focus:border-[var(--border-focus)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-accent)]/50';

function toDate(value: string | null): Date | null {
  if (!value) return null;
  const parsed = parseISO(value);
  return isValid(parsed) ? parsed : null;
}

interface Draft {
  start: Date | null;
  end: Date | null;
}

interface RangeMonthProps {
  viewMonth: Date;
  draft: Draft;
  today: Date;
  onPick: (day: Date) => void;
}

function RangeMonth({ viewMonth, draft, today, onPick }: RangeMonthProps) {
  const days = eachDayOfInterval({
    start: startOfWeek(startOfMonth(viewMonth), { weekStartsOn: 1 }),
    end: endOfWeek(endOfMonth(viewMonth), { weekStartsOn: 1 }),
  });

  const inRange = (day: Date) =>
    !!draft.start &&
    !!draft.end &&
    (isAfter(day, draft.start) || isSameDay(day, draft.start)) &&
    (isBefore(day, draft.end) || isSameDay(day, draft.end));

  return (
    <div className="w-[228px]">
      <div className="mb-1 grid grid-cols-7 gap-0.5">
        {WEEKDAYS.map((d) => (
          <div key={d} className="text-center text-[11px] font-medium text-[var(--text-muted)]">
            {d}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-0.5">
        {days.map((day) => {
          const disabled = isAfter(day, today);
          const outside = !isSameMonth(day, viewMonth);
          const isEndpoint =
            (draft.start && isSameDay(day, draft.start)) ||
            (draft.end && isSameDay(day, draft.end));
          const between = !isEndpoint && inRange(day);
          return (
            <button
              key={day.toISOString()}
              type="button"
              disabled={disabled}
              onClick={() => onPick(day)}
              className={cn(
                'flex h-8 w-8 items-center justify-center rounded-[var(--radius-default)] text-[13px] transition-colors',
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-accent)]',
                disabled && 'cursor-not-allowed opacity-30',
                !disabled && !isEndpoint && !between && 'text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]',
                outside && !isEndpoint && !between && 'text-[var(--text-muted)]',
                between && 'bg-[var(--surface-brand-subtle)] text-[var(--text-primary)]',
                isToday(day) && !isEndpoint && 'ring-1 ring-[var(--border-focus)]',
                isEndpoint && 'rounded bg-[var(--interactive-primary)] font-medium text-white',
              )}
            >
              {format(day, 'd')}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function DateRangePicker({
  presets,
  activePreset,
  from,
  to,
  onPresetSelect,
  onCustomRange,
  className,
}: DateRangePickerProps) {
  const [open, setOpen] = useState(false);
  const today = new Date();

  const fromDate = toDate(from);
  const toDateValue = toDate(to);

  // Local draft so a half-finished selection never re-queries the parent.
  const [draft, setDraft] = useState<Draft>({ start: fromDate, end: toDateValue });
  const [viewMonth, setViewMonth] = useState<Date>(fromDate ?? today);

  // Reseed from props on open (event handler, not effect) so it reflects current state.
  function handleOpenChange(next: boolean) {
    if (next) {
      const seedStart = toDate(from);
      setDraft({ start: seedStart, end: toDate(to) });
      setViewMonth(seedStart ?? new Date());
    }
    setOpen(next);
  }

  const nextMonthDisabled = !isBefore(startOfMonth(viewMonth), startOfMonth(today));

  function handlePick(day: Date) {
    // First click (or restart after a complete range) seeds start, clears end.
    if (!draft.start || draft.end) {
      setDraft({ start: day, end: null });
      return;
    }
    // Second click sets end; swap so start ≤ end.
    let start = draft.start;
    let end = day;
    if (isBefore(end, start)) {
      [start, end] = [end, start];
    }
    setDraft({ start, end });
    onCustomRange(format(start, 'yyyy-MM-dd'), format(end, 'yyyy-MM-dd'));
    setOpen(false);
  }

  function handlePreset(id: string) {
    onPresetSelect(id);
    setOpen(false);
  }

  const triggerLabel = (() => {
    if (activePreset) {
      return presets.find((p) => p.id === activePreset)?.label ?? 'Date range';
    }
    if (fromDate && toDateValue) {
      return `${format(fromDate, 'd MMM')} – ${format(toDateValue, 'd MMM yyyy')}`;
    }
    return 'Date range';
  })();

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <button type="button" className={cn(TRIGGER_CLASS, className)}>
          <CalendarIcon className="h-3.5 w-3.5 shrink-0 text-[var(--text-muted)]" />
          <span className="truncate">{triggerLabel}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" side="bottom" className="p-0">
        <div className="flex">
          <div className="flex w-[148px] flex-col gap-0.5 border-r border-[var(--border-default)] p-2">
            {presets.map((preset) => (
              <button
                key={preset.id}
                type="button"
                onClick={() => handlePreset(preset.id)}
                className={cn(
                  'rounded-[var(--radius-default)] px-2.5 py-1.5 text-left text-[13px] transition-colors',
                  preset.id === activePreset
                    ? 'bg-[var(--surface-brand-subtle)] text-[var(--interactive-primary)]'
                    : 'text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]',
                )}
              >
                {preset.label}
              </button>
            ))}
          </div>

          <div className="p-3">
            <div className="mb-2 flex items-center justify-between">
              <button
                type="button"
                aria-label="Previous month"
                onClick={() => setViewMonth((m) => subMonths(m, 1))}
                className="rounded-[var(--radius-default)] p-1 text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <div className="flex flex-1 items-center justify-around text-[13px] font-medium text-[var(--text-primary)]">
                <span>{format(viewMonth, 'MMMM yyyy')}</span>
                <span>{format(addMonths(viewMonth, 1), 'MMMM yyyy')}</span>
              </div>
              <button
                type="button"
                aria-label="Next month"
                disabled={nextMonthDisabled}
                onClick={() => setViewMonth((m) => addMonths(m, 1))}
                className={cn(
                  'rounded-[var(--radius-default)] p-1 text-[var(--text-secondary)]',
                  nextMonthDisabled
                    ? 'cursor-not-allowed opacity-30'
                    : 'hover:bg-[var(--bg-secondary)]',
                )}
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
            <div className="flex gap-4">
              <RangeMonth viewMonth={viewMonth} draft={draft} today={today} onPick={handlePick} />
              <RangeMonth
                viewMonth={addMonths(viewMonth, 1)}
                draft={draft}
                today={today}
                onPick={handlePick}
              />
            </div>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
