import { cn } from '@/utils/cn';

export interface DateRangeFieldProps {
  from: string;
  to: string;
  onFromChange: (value: string) => void;
  onToChange: (value: string) => void;
  className?: string;
  /** Shared input class so callers match their surrounding control styling. */
  inputClassName?: string;
}

const DEFAULT_INPUT_CLASS =
  'w-full rounded-[var(--radius-default)] border border-[var(--border-default)] bg-[var(--bg-primary)] px-2.5 py-1.5 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-accent)]/50';

export function DateRangeField({
  from,
  to,
  onFromChange,
  onToChange,
  className,
  inputClassName,
}: DateRangeFieldProps) {
  const inputClass = inputClassName ?? DEFAULT_INPUT_CLASS;
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <input
        type="date"
        value={from}
        onChange={(e) => onFromChange(e.target.value)}
        className={inputClass}
      />
      <span className="text-[var(--text-muted)]">–</span>
      <input
        type="date"
        value={to}
        onChange={(e) => onToChange(e.target.value)}
        className={inputClass}
      />
    </div>
  );
}
