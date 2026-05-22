import { useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import {
  format,
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

const WEEKDAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'] as const;

export interface CalendarProps {
  value: Date | null;
  onSelect: (date: Date) => void;
  /** Inclusive lower bound; earlier days and months are neither shown nor reachable. */
  min?: Date | null;
  /** Inclusive upper bound; later days and months are neither shown nor reachable. */
  max?: Date | null;
  className?: string;
}

export function Calendar({ value, onSelect, min, max, className }: CalendarProps) {
  // Open on the selected month, or the latest month still within range.
  const initialMonth = value ?? (max && isBefore(max, new Date()) ? max : new Date());
  const [viewMonth, setViewMonth] = useState<Date>(initialMonth);

  const days = eachDayOfInterval({
    start: startOfWeek(startOfMonth(viewMonth), { weekStartsOn: 1 }),
    end: endOfWeek(endOfMonth(viewMonth), { weekStartsOn: 1 }),
  });

  const outOfRange = (day: Date) =>
    (min ? isBefore(day, min) : false) || (max ? isAfter(day, max) : false);

  // Cap navigation at the bounds so out-of-range months can never be displayed.
  const prevDisabled = min ? !isAfter(startOfMonth(viewMonth), startOfMonth(min)) : false;
  const nextDisabled = max ? !isBefore(startOfMonth(viewMonth), startOfMonth(max)) : false;

  return (
    <div className={cn('w-[244px] p-3', className)}>
      <div className="mb-2 flex items-center justify-between">
        <button
          type="button"
          aria-label="Previous month"
          disabled={prevDisabled}
          onClick={() => setViewMonth((m) => subMonths(m, 1))}
          className={cn(
            'rounded-[var(--radius-default)] p-1 text-[var(--text-secondary)]',
            prevDisabled ? 'cursor-not-allowed opacity-30' : 'hover:bg-[var(--bg-secondary)]',
          )}
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <span className="text-[13px] font-medium text-[var(--text-primary)]">
          {format(viewMonth, 'MMMM yyyy')}
        </span>
        <button
          type="button"
          aria-label="Next month"
          disabled={nextDisabled}
          onClick={() => setViewMonth((m) => addMonths(m, 1))}
          className={cn(
            'rounded-[var(--radius-default)] p-1 text-[var(--text-secondary)]',
            nextDisabled ? 'cursor-not-allowed opacity-30' : 'hover:bg-[var(--bg-secondary)]',
          )}
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>

      <div className="mb-1 grid grid-cols-7 gap-0.5">
        {WEEKDAYS.map((d) => (
          <div
            key={d}
            className="text-center text-[11px] font-medium text-[var(--text-muted)]"
          >
            {d}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-0.5">
        {days.map((day) => {
          // Out-of-range days are not rendered at all — no greyed-out future.
          if (outOfRange(day)) {
            return <div key={day.toISOString()} className="h-8 w-8" aria-hidden />;
          }
          const selected = value ? isSameDay(day, value) : false;
          const outside = !isSameMonth(day, viewMonth);
          return (
            <button
              key={day.toISOString()}
              type="button"
              onClick={() => onSelect(day)}
              className={cn(
                'flex h-8 w-8 items-center justify-center rounded-[var(--radius-default)] text-[13px] transition-colors',
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-accent)]',
                !selected && 'text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]',
                outside && !selected && 'text-[var(--text-muted)]',
                isToday(day) && !selected && 'font-semibold text-[var(--text-brand)]',
                selected && 'bg-[var(--interactive-primary)] font-medium text-[var(--text-on-color)]',
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
