/**
 * MetricChip — compact label+value pair used in record-detail summary rails.
 *
 * A low-chrome alternative to the square "KPI tile" — no background, just a
 * tight label + value stack with optional sub-line. Designed to sit in a
 * vertical rail or an inline flex group.
 *
 * Kept generic (no CRM vocabulary) so any detail page can use it.
 */

import type { ReactNode } from 'react';
import { cn } from '@/utils';

export type MetricChipTone = 'neutral' | 'brand' | 'success' | 'warning' | 'info';

interface MetricChipProps {
  label: string;
  value: ReactNode;
  /** Optional dim sub-line (units, SLA, context). */
  sub?: ReactNode;
  /**
   * Direct colour override for the value (e.g. `text-[var(--color-success)]`).
   * Takes precedence over `tone` when set — used for context-sensitive
   * one-off colouring (e.g. FRT RAG bands).
   */
  valueClass?: string;
  /** Semantic tone — drives value colour + left accent bar when the chip is in `stack` layout. */
  tone?: MetricChipTone;
  /** Layout hint. Defaults to 'stack'. */
  layout?: 'stack' | 'inline';
  className?: string;
}

const TONE_VALUE_CLASS: Record<MetricChipTone, string> = {
  neutral: 'text-[var(--text-primary)]',
  brand: 'text-[var(--text-brand)]',
  success: 'text-[var(--color-success)]',
  warning: 'text-[var(--color-warning)]',
  info: 'text-[var(--color-info)]',
};

const TONE_BAR_CLASS: Record<MetricChipTone, string> = {
  neutral: 'bg-[var(--border-subtle)]',
  brand: 'bg-[var(--border-brand)]',
  success: 'bg-[var(--color-success)]',
  warning: 'bg-[var(--color-warning)]',
  info: 'bg-[var(--color-info)]',
};

export function MetricChip({
  label,
  value,
  sub,
  valueClass,
  tone = 'neutral',
  layout = 'stack',
  className,
}: MetricChipProps) {
  const resolvedValueClass = valueClass ?? TONE_VALUE_CLASS[tone];

  if (layout === 'inline') {
    return (
      <div className={cn('flex items-baseline gap-2 text-xs', className)}>
        <span className="text-[var(--text-muted)] whitespace-nowrap">{label}</span>
        <span className={cn('tabular-nums font-medium', resolvedValueClass)}>{value}</span>
        {sub && <span className="text-[10px] text-[var(--text-muted)]">{sub}</span>}
      </div>
    );
  }

  return (
    <div className={cn('relative flex flex-col gap-0.5 pl-2.5', className)}>
      {/* Tonal accent bar. Neutral is a muted hairline so every chip looks
          structurally the same — tone just shifts colour, not layout. */}
      <span
        aria-hidden
        className={cn(
          'absolute left-0 top-[2px] bottom-[2px] w-[2px] rounded-full',
          TONE_BAR_CLASS[tone],
          tone === 'neutral' && 'opacity-70',
        )}
      />
      <span className="text-[10px] uppercase tracking-[0.08em] text-[var(--text-muted)]">
        {label}
      </span>
      <span className={cn('text-sm font-semibold tabular-nums', resolvedValueClass)}>
        {value}
      </span>
      {sub && <span className="text-[11px] text-[var(--text-muted)]">{sub}</span>}
    </div>
  );
}
