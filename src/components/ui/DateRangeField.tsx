import { useState } from 'react';
import { Calendar as CalendarIcon } from 'lucide-react';
import { format, parseISO, isValid } from 'date-fns';
import { cn } from '@/utils/cn';
import { Popover, PopoverTrigger, PopoverContent } from './Popover';
import { Calendar } from './Calendar';

export interface DateRangeFieldProps {
  from: string;
  to: string;
  onFromChange: (value: string) => void;
  onToChange: (value: string) => void;
  className?: string;
  /** Shared class so callers match their surrounding control styling. */
  inputClassName?: string;
}

const TRIGGER_BASE =
  'flex flex-1 min-w-0 items-center gap-2 rounded-[var(--radius-default)] border border-[var(--border-default)] bg-[var(--bg-primary)] px-2.5 py-1.5 text-[13px] text-[var(--text-primary)] focus:border-[var(--border-focus)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-accent)]/50';

function toDate(value: string): Date | null {
  if (!value) return null;
  const parsed = parseISO(value);
  return isValid(parsed) ? parsed : null;
}

interface DateEndpointProps {
  value: string;
  placeholder: string;
  min?: Date | null;
  max?: Date | null;
  onChange: (value: string) => void;
  triggerClass: string;
}

function DateEndpoint({ value, placeholder, min, max, onChange, triggerClass }: DateEndpointProps) {
  const [open, setOpen] = useState(false);
  const selected = toDate(value);
  const label = selected ? format(selected, 'd MMM yyyy') : null;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className={triggerClass}>
          <CalendarIcon className="h-3.5 w-3.5 shrink-0 text-[var(--text-muted)]" />
          <span className={cn('truncate', !label && 'text-[var(--text-muted)]')}>
            {label ?? placeholder}
          </span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="p-0">
        <Calendar
          value={selected}
          min={min}
          max={max}
          onSelect={(date) => {
            onChange(format(date, 'yyyy-MM-dd'));
            setOpen(false);
          }}
        />
      </PopoverContent>
    </Popover>
  );
}

export function DateRangeField({
  from,
  to,
  onFromChange,
  onToChange,
  className,
  inputClassName,
}: DateRangeFieldProps) {
  const triggerClass = cn(TRIGGER_BASE, inputClassName);
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <DateEndpoint
        value={from}
        placeholder="From"
        max={toDate(to)}
        onChange={onFromChange}
        triggerClass={triggerClass}
      />
      <span className="text-[var(--text-muted)]">–</span>
      <DateEndpoint
        value={to}
        placeholder="To"
        min={toDate(from)}
        onChange={onToChange}
        triggerClass={triggerClass}
      />
    </div>
  );
}
