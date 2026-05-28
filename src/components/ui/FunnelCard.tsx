import type { ReactNode } from 'react';
import { Card } from './Card';
import { cn } from '@/utils/cn';

export interface FunnelStageDatum {
  key: string;
  label: string;
  value: number;
}

interface FunnelCardProps {
  title: string;
  stages: FunnelStageDatum[];
  /** Optional control rendered in the header (e.g. a campaign picker). */
  headerControl?: ReactNode;
}

/** Channel-adaptive conversion funnel. Stage keys/labels come from the API
 *  (`funnel_stages`) so the viz never hardcodes a vendor's stage names. Each
 *  bar widths proportional to the first (widest) stage. */
export function FunnelCard({ title, stages, headerControl }: FunnelCardProps) {
  const top = stages.length ? Math.max(...stages.map((s) => s.value)) : 0;

  return (
    <Card className="flex h-full min-h-0 flex-col p-4">
      <div className="mb-3 flex shrink-0 items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
        {headerControl}
      </div>
      {stages.length === 0 ? (
        <p className="py-6 text-center text-xs text-[var(--text-muted)]">No funnel data</p>
      ) : (
        <ul className="flex flex-col gap-2.5">
          {stages.map((stage) => {
            const pct = top ? (stage.value / top) * 100 : 0;
            const conversion = top ? (stage.value / top) * 100 : 0;
            return (
              <li key={stage.key} className="flex flex-col gap-1">
                <div className="flex items-baseline justify-between gap-2 text-[13px]">
                  <span className="text-[var(--text-secondary)]">{stage.label}</span>
                  <span className="flex items-baseline gap-2">
                    <span className="font-semibold tabular-nums text-[var(--text-primary)]">
                      {stage.value}
                    </span>
                    <span className="text-[11px] tabular-nums text-[var(--text-muted)]">
                      {conversion.toFixed(0)}%
                    </span>
                  </span>
                </div>
                <span className="h-2.5 w-full overflow-hidden rounded-full bg-[var(--bg-tertiary)]">
                  <span
                    className={cn('block h-full rounded-full bg-[var(--interactive-primary)]')}
                    style={{ width: `${pct > 0 ? Math.max(pct, 3) : 0}%` }}
                  />
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
