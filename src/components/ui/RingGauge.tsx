import type { CSSProperties, ReactNode } from 'react';
import { cn } from '@/utils';

export type RingGaugeTone = 'accent' | 'success' | 'warning' | 'error' | 'neutral';

interface RingGaugeProps {
  /** 0..1 fraction; values outside are clamped. */
  value: number;
  /** Center label (defaults to rounded percent). */
  centerLabel?: ReactNode;
  tone?: RingGaugeTone;
  size?: number;
  thickness?: number;
  className?: string;
}

const TONE_COLOR: Record<RingGaugeTone, string> = {
  accent: 'var(--color-brand-primary)',
  success: 'var(--color-success)',
  warning: 'var(--color-warning)',
  error: 'var(--color-error)',
  neutral: 'var(--text-muted)',
};

export function RingGauge({
  value,
  centerLabel,
  tone = 'accent',
  size = 84,
  thickness = 10,
  className,
}: RingGaugeProps) {
  const pct = Math.max(0, Math.min(1, value));
  const pctLabel = `${Math.round(pct * 100)}%`;
  const ringColor = TONE_COLOR[tone];
  const style: CSSProperties = {
    width: size,
    height: size,
    background: `conic-gradient(${ringColor} ${pct * 360}deg, var(--bg-tertiary) 0)`,
  };
  const innerStyle: CSSProperties = {
    inset: thickness,
    background: 'var(--bg-elevated)',
  };
  return (
    <div
      role="img"
      aria-label={`${pctLabel} ${tone}`}
      className={cn('relative grid place-items-center rounded-full', className)}
      style={style}
    >
      <span className="absolute rounded-full" style={innerStyle} />
      <span className="relative z-[1] text-sm font-semibold tabular-nums text-[var(--text-primary)]">
        {centerLabel ?? pctLabel}
      </span>
    </div>
  );
}
