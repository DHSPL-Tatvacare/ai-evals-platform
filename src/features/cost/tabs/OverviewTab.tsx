import { useEffect } from 'react';
import { BarChart3, Sparkles } from 'lucide-react';
import { Card } from '@/components/ui';
import { useCostStore } from '@/stores/costStore';
import { ChartRenderer } from '@/features/analytics/components/ChartRenderer';
import { cn } from '@/utils/cn';
import { CostKpiRow } from '../components/CostKpiRow';
import { SliceStateBoundary } from '../components/SliceStateBoundary';
import { formatInt, formatUsdCompact } from '../utils/format';
import type { CostOverview, CostKpi, GroupedSpend } from '../types';

interface TabProps {
  active: boolean;
}

export function OverviewTab({ active }: TabProps) {
  const slice = useCostStore((s) => s.overview);
  const loadOverview = useCostStore((s) => s.loadOverview);
  const refresh = useCostStore((s) => s.refreshActive);
  const filtersKey = useCostStore((s) => s.filtersKey);

  useEffect(() => {
    if (active) void loadOverview();
  }, [active, loadOverview, filtersKey]);

  return (
    <div className="flex h-full min-h-0 flex-col space-y-4 pb-6">
      <SliceStateBoundary
        slice={slice}
        onRetry={() => refresh('overview')}
        emptyIcon={BarChart3}
        emptyTitle="No usage yet"
        emptyDescription="No LLM requests were recorded for the selected range."
        isEmpty={(data) => data.kpis.totalCalls === 0}
      >
        {(data) => <OverviewContent data={data} />}
      </SliceStateBoundary>
    </div>
  );
}

function OverviewContent({ data }: { data: CostOverview }) {
  return (
    <>
      <AiSummaryBox kpis={data.kpis} byApp={data.spendByApp} />

      <CostKpiRow kpis={data.kpis} />

      <Card className="p-4">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">Daily spend</h2>
          <span className="text-[11.5px] text-[var(--text-muted)]">{data.timeSeries.length} days</span>
        </div>
        <ChartRenderer
          type="area"
          data={data.timeSeries as unknown as Record<string, unknown>[]}
          xKey="day"
          yKey="costUsd"
          legendPosition="none"
          height={260}
        />
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <SpendDonutCard
          title="By app"
          rows={data.spendByApp}
        />
        <SpendDonutCard
          title="By purpose"
          rows={data.spendByPurpose}
        />
      </div>
    </>
  );
}

interface Signal {
  key: string;
  tone: 'warning' | 'error' | 'info';
  body: React.ReactNode;
}

function AiSummaryBox({ kpis, byApp }: { kpis: CostKpi; byApp: GroupedSpend[] }) {
  const topApp = byApp[0];
  const signals: Signal[] = [];

  if (kpis.pricingFallbackCalls > 0) {
    signals.push({
      key: 'unpriced',
      tone: 'warning',
      body: (
        <>
          <span className="tabular-nums">{formatInt(kpis.pricingFallbackCalls)}</span> requests priced with a
          fallback rate &mdash; add a pricing row to stop under-accounting for spend.
        </>
      ),
    });
  }
  if (kpis.errorCalls > 0) {
    const errorPct = kpis.totalCalls ? kpis.errorCalls / kpis.totalCalls : 0;
    signals.push({
      key: 'errors',
      tone: errorPct > 0.02 ? 'error' : 'info',
      body: (
        <>
          <span className="tabular-nums">{formatInt(kpis.errorCalls)}</span> failed requests
          {kpis.totalCalls > 0 && <> &middot; {(errorPct * 100).toFixed(2)}% of traffic</>}.
        </>
      ),
    });
  }
  if (topApp && byApp.length > 1) {
    const total = byApp.reduce((s, r) => s + r.costUsd, 0);
    const share = total ? topApp.costUsd / total : 0;
    if (share >= 0.5) {
      signals.push({
        key: 'concentration',
        tone: 'info',
        body: (
          <>
            <span className="font-medium text-[var(--text-primary)]">{topApp.key}</span> drives{' '}
            {(share * 100).toFixed(0)}% of all spend ({formatUsdCompact(topApp.costUsd)}).
          </>
        ),
      });
    }
  }

  return (
    <div className="rounded-[var(--radius-lg)] bg-[var(--gradient-node-ai)] p-px shadow-[var(--shadow-md)]">
      <div className="rounded-[7px] bg-[var(--surface-node-ai)] p-5">
        <div className="mb-3.5 flex items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-lg)] bg-[var(--gradient-node-ai)] shadow-[var(--shadow-sm)]">
            <Sparkles className="h-[18px] w-[18px] text-white" />
          </span>
          <div className="flex flex-col">
            <h3 className="bg-[var(--gradient-brand-text)] bg-clip-text text-[15px] font-semibold leading-tight text-transparent">
              Signals to watch
            </h3>
            <span className="text-[11px] font-medium uppercase tracking-wide text-[var(--text-muted)]">AI summary</span>
          </div>
        </div>
        {signals.length === 0 ? (
          <p className="text-[13px] leading-relaxed text-[var(--text-secondary)]">
            Nothing unusual &mdash; no unpriced rows, errors within norm, spend balanced across apps.
          </p>
        ) : (
          <ul className="space-y-2">
            {signals.map((signal) => (
              <li key={signal.key} className="flex items-start gap-2.5 text-[13px] leading-relaxed text-[var(--text-secondary)]">
                <span
                  className={cn(
                    'mt-[6px] h-1.5 w-1.5 shrink-0 rounded-full',
                    signal.tone === 'warning' && 'bg-[var(--color-warning)]',
                    signal.tone === 'error' && 'bg-[var(--color-error)]',
                    signal.tone === 'info' && 'bg-[var(--color-info)]',
                  )}
                />
                <span>{signal.body}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function SpendDonutCard({ title, rows }: { title: string; rows: GroupedSpend[] }) {
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
        <span className="text-[11.5px] text-[var(--text-muted)]">share of spend</span>
      </div>
      {rows.length === 0 ? (
        <p className="py-6 text-center text-xs text-[var(--text-muted)]">No spend recorded</p>
      ) : (
        <ChartRenderer
          type="donut"
          data={rows.map((r) => ({ name: r.key, value: r.costUsd }))}
          xKey="name"
          yKey="value"
          height={260}
          legendPosition="right"
          // compact suppresses overlapping slice labels — legend + hover tooltip carry the detail
          compact
        />
      )}
    </Card>
  );
}
