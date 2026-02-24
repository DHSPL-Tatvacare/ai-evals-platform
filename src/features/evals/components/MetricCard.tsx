import { Info, UserCheck } from 'lucide-react';
import { Tooltip } from '@/components/ui';
import { cn } from '@/utils';
import { getRatingColors, type MetricResult } from '../metrics';

interface MetricCardProps {
  metric: MetricResult;
  compact?: boolean;
}

function MetricTooltipContent({ metric }: { metric: MetricResult }) {
  const lines = metric.tooltip?.split('\n') ?? [];
  return (
    <div className="space-y-1">
      {lines[0] && <p>{lines[0]}</p>}
      {lines[1] && (
        <p className="font-mono text-[11px] text-[var(--text-muted)]">{lines[1]}</p>
      )}
      {metric.description && (
        <p className="text-[11px] text-[var(--text-muted)]">{metric.description}</p>
      )}
    </div>
  );
}

function InfoIcon({ metric }: { metric: MetricResult }) {
  if (!metric.tooltip) return null;
  return (
    <Tooltip content={<MetricTooltipContent metric={metric} />} position="bottom">
      <Info className="h-3 w-3 text-[var(--text-muted)] cursor-help shrink-0" />
    </Tooltip>
  );
}

/** Small indicator shown when metric was recomputed with human review */
function HumanSourceIcon() {
  return (
    <Tooltip
      content="Recomputed with human review adjustments"
      position="bottom"
    >
      <UserCheck className="h-3 w-3 text-[var(--color-brand-primary)] cursor-help shrink-0" />
    </Tooltip>
  );
}

export function MetricCard({ metric, compact = false }: MetricCardProps) {
  const colors = getRatingColors(metric.rating);
  const isHumanSource = metric.source === 'human';

  if (compact) {
    return (
      <div className={cn('rounded-lg border border-[var(--border-subtle)] px-3 py-2', colors.bg)}>
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1 text-[11px] font-medium text-[var(--text-secondary)]">
            {metric.label}
            <InfoIcon metric={metric} />
            {isHumanSource && <HumanSourceIcon />}
          </span>
          <span className={cn('text-[13px] font-semibold', colors.text)}>
            {metric.displayValue}
          </span>
        </div>
        <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-[var(--bg-tertiary)]">
          <div
            className={cn('h-full rounded-full transition-all', colors.bar)}
            style={{ width: `${Math.min(metric.percentage, 100)}%` }}
          />
        </div>
      </div>
    );
  }

  return (
    <div className={cn('rounded-lg border border-[var(--border-subtle)] p-3', colors.bg)}>
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1 text-[11px] font-medium uppercase tracking-wide text-[var(--text-muted)]">
          {metric.label}
          <InfoIcon metric={metric} />
          {isHumanSource && <HumanSourceIcon />}
        </span>
        <span className={cn('text-[15px] font-bold', colors.text)}>
          {metric.displayValue}
        </span>
      </div>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-tertiary)]">
        <div
          className={cn('h-full rounded-full transition-all duration-300', colors.bar)}
          style={{ width: `${Math.min(metric.percentage, 100)}%` }}
        />
      </div>
      <div className="mt-1.5 text-center">
        <span className={cn('text-[10px] font-medium capitalize', colors.text)}>
          {metric.rating}
        </span>
      </div>
    </div>
  );
}
