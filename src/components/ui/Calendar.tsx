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
  /** Inclusive lower bound; days before it are disabled. */
  min?: Date | null;
  /** Inclusive upper bound; days after it are disabled. */
  max?: Date | null;
  className?: string;
}

export function Calendar({ value, onSelect, min, max, className }: CalendarProps) {
  const [viewMonth, setViewMonth] = useState<Date>(value ?? new Date());

  const days = eachDayOfInterval({
    start: startOfWeek(startOfMonth(viewMonth), { weekStartsOn: 1 }),
    end: endOfWeek(endOfMonth(viewMonth), { weekStartsOn: 1 }),
  });

  const disabledFor = (day: Date) =>
    (min ? isBefore(day, min) : false) || (max ? isAfter(day, max) : false);

  return (
    <div className={cn('w-[244px] p-3', className)}>
      <div className="mb-2 flex items-center justify-between">
        <button
          type="button"
          aria-label="Previous month"
          onClick={() => setViewMonth((m) => subMonths(m, 1))}
          className="rounded-[var(--radius-default)] p-1 text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <span className="text-[13px] font-medium text-[var(--text-primary)]">
          {format(viewMonth, 'MMMM yyyy')}
        </span>
        <button
          type="button"
          aria-label="Next month"
          onClick={() => setViewMonth((m) => addMonths(m, 1))}
          className="rounded-[var(--radius-default)] p-1 text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]"
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
          const selected = value ? isSameDay(day, value) : false;
          const outside = !isSameMonth(day, viewMonth);
          const disabled = disabledFor(day);
          return (
            <button
              key={day.toISOString()}
              type="button"
              disabled={disabled}
              onClick={() => onSelect(day)}
              className={cn(
                'flex h-8 w-8 items-center justify-center rounded-[var(--radius-default)] text-[13px] transition-colors',
                'focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-accent)]',
                !disabled && !selected && 'text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]',
                outside && !selected && 'text-[var(--text-muted)]',
                isToday(day) && !selected && 'font-semibold text-[var(--text-brand)]',
                selected && 'bg-[var(--interactive-primary)] font-medium text-[var(--text-on-color)]',
                disabled && 'cursor-not-allowed text-[var(--text-muted)] opacity-40',
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
