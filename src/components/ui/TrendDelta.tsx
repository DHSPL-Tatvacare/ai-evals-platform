import type { ReactNode } from 'react';
import { ArrowUpRight, ArrowDownRight, Minus } from 'lucide-react';
import { cn } from '@/utils';

export type TrendSemantic = 'cost' | 'positive' | 'neutral';

interface TrendDeltaProps {
  /** Signed delta. Positive = up arrow. Zero/undefined = flat. */
  value: number | null | undefined;
  /**
   * Interpretation:
   *  - 'cost' → up is bad (red), down is good (green). Default for cost dashboards.
   *  - 'positive' → up is good (green), down is bad (red).
   *  - 'neutral' → up = muted arrow, no tone coloring.
   */
  semantic?: TrendSemantic;
  /** Format the numeric value (e.g. percent, pp). Overrides default percent. */
  format?: (v: number) => string;
  /** Suffix rendered after the number (e.g. "vs prev 30d"). */
  suffix?: ReactNode;
  className?: string;
}

function defaultFormat(v: number): string {
  const sign = v > 0 ? '+' : '';
  return `${sign}${(v * 100).toFixed(1)}%`;
}

export function TrendDelta({ value, semantic = 'cost', format, suffix, className }: TrendDeltaProps) {
  if (value == null || !Number.isFinite(value) || value === 0) {
    return (
      <span
        className={cn(
          'inline-flex items-center gap-1 text-[11.5px] text-[var(--text-muted)]',
          className,
        )}
      >
        <Minus className="h-3 w-3" aria-hidden />
        <span className="tabular-nums">±0%</span>
        {suffix}
      </span>
    );
  }
  const isUp = value > 0;
  let colorClass = 'text-[var(--text-muted)]';
  if (semantic === 'cost') {
    colorClass = isUp ? 'text-[var(--color-error)]' : 'text-[var(--color-success)]';
  } else if (semantic === 'positive') {
    colorClass = isUp ? 'text-[var(--color-success)]' : 'text-[var(--color-error)]';
  }
  const Icon = isUp ? ArrowUpRight : ArrowDownRight;
  const label = (format ?? defaultFormat)(value);
  return (
    <span className={cn('inline-flex items-center gap-1 text-[11.5px]', colorClass, className)}>
      <Icon className="h-3 w-3" aria-hidden />
      <span className="tabular-nums">{label}</span>
      {suffix && <span className="text-[var(--text-muted)]">{suffix}</span>}
    </span>
  );
}
