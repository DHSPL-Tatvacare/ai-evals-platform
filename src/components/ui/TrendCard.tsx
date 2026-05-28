import type { ReactNode } from 'react';
import { Card } from './Card';
import { ChartRenderer } from '@/features/analytics/components/ChartRenderer';

interface TrendCardProps {
  title: string;
  data: Record<string, unknown>[];
  xKey: string;
  /** Stacked series keys (one per outcome bucket). */
  seriesKeys: string[];
  height?: number;
  /** Optional control rendered in the header. */
  headerControl?: ReactNode;
  subtitle?: string;
}

/** Stacked-area trend share-card. Wraps the shared ChartRenderer so trend
 *  surfaces across the platform read the same. */
export function TrendCard({
  title,
  data,
  xKey,
  seriesKeys,
  height = 260,
  headerControl,
  subtitle,
}: TrendCardProps) {
  return (
    <Card className="flex h-full min-h-0 flex-col p-4">
      <div className="mb-2 flex shrink-0 items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
        {headerControl ?? (subtitle && <span className="text-[11.5px] text-[var(--text-muted)]">{subtitle}</span>)}
      </div>
      {data.length === 0 ? (
        <p className="py-6 text-center text-xs text-[var(--text-muted)]">No trend data</p>
      ) : (
        <ChartRenderer
          type="area"
          data={data}
          xKey={xKey}
          seriesKeys={seriesKeys}
          legendPosition="top"
          height={height}
        />
      )}
    </Card>
  );
}
