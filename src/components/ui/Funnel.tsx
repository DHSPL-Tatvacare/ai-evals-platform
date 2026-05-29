import { cn } from '@/utils/cn';

export interface FunnelStage {
  key: string;
  label: string;
  count: number;
}

interface FunnelProps {
  /** Ordered stage list, root first. Widths derive from the root (stages[0]). */
  stages: FunnelStage[];
  /** A4 / light-friendly rendering for PDF export. */
  printMode?: boolean;
  className?: string;
}

interface ComputedStage extends FunnelStage {
  pctOfRoot: number;
  width: number;
  dropPct: number | null;
}

function computeStages(stages: FunnelStage[]): ComputedStage[] {
  const root = stages.length ? stages[0].count : 0;
  return stages.map((stage, index) => {
    const ratio = root > 0 ? stage.count / root : 0;
    const prev = index > 0 ? stages[index - 1].count : null;
    const dropPct =
      prev === null ? null : prev > 0 ? (1 - stage.count / prev) * 100 : 0;
    return {
      ...stage,
      pctOfRoot: ratio * 100,
      width: ratio * 100,
      dropPct,
    };
  });
}

/** A true centered, tapering funnel for an ordered, root-first stage list.
 *  Knows nothing about channels, providers, or stage names — labels and counts
 *  come only from `stages`. Each band's width is `count / root` (centered);
 *  per stage we show label, count, %-of-root and the step drop-off vs the
 *  previous stage (first stage has none). */
export function Funnel({ stages, className }: FunnelProps) {
  if (stages.length === 0) {
    return (
      <p className={cn('py-6 text-center text-xs text-[var(--text-muted)]', className)}>
        No funnel data
      </p>
    );
  }

  const computed = computeStages(stages);
  const multiStage = computed.length > 1;

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      {computed.map((stage, index) => {
        const isLast = index === computed.length - 1;
        return (
          <div key={stage.key} data-funnel-stage className="flex flex-col gap-1">
            {/* Label line — full width, never truncated. */}
            <div className="flex items-baseline justify-between gap-3 text-[13px]">
              <span className="whitespace-nowrap font-medium text-[var(--text-secondary)]">
                {stage.label}
              </span>
              <span className="flex items-baseline gap-2 whitespace-nowrap">
                <span className="font-semibold tabular-nums text-[var(--text-primary)]">
                  {stage.count}
                </span>
                <span className="tabular-nums text-[11px] text-[var(--text-muted)]">
                  {Math.round(stage.pctOfRoot)}%
                </span>
                {stage.dropPct !== null ? (
                  <span
                    data-testid="funnel-dropoff"
                    className="tabular-nums text-[11px] text-[var(--text-muted)]"
                  >
                    {stage.dropPct > 0 ? `▼${Math.round(stage.dropPct)}%` : '0%'}
                  </span>
                ) : null}
              </span>
            </div>
            {/* Centered tapering band. */}
            <div className="relative flex h-7 items-center justify-center" aria-hidden>
              <div
                data-funnel-band={stage.key}
                data-testid={`funnel-band-${stage.key}`}
                className="h-full rounded-[4px] bg-[var(--interactive-primary)]"
                style={{ width: `${Math.max(stage.width, stage.count > 0 ? 2 : 0)}%` }}
              />
            </div>
            {/* Tapered connector to the next stage. */}
            {multiStage && !isLast && (
              <div className="relative flex h-1.5 items-center justify-center" aria-hidden>
                <div
                  className="h-full rounded-[2px] bg-[var(--interactive-primary)] opacity-25"
                  style={{ width: `${Math.min(stage.width, computed[index + 1].width)}%` }}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
