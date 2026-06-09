import { useEffect } from 'react';
import { BarChart3, Sparkles } from 'lucide-react';
import { Card } from '@/components/ui';
import { useCostStore } from '@/stores/costStore';
import { ChartRenderer } from '@/features/analytics/components/ChartRenderer';
import { cn } from '@/utils/cn';
import { CostKpiRow } from '../components/CostKpiRow';
import { SliceStateBoundary } from '../components/SliceStateBoundary';
import { formatInt, formatUsdCompact, formatDateTime } from '../utils/format';
import type { CostOverview, CostKpi, CostSignalsSnapshot, GroupedSpend } from '../types';

interface TabProps {
  active: boolean;
}

export function OverviewTab({ active }: TabProps) {
  const slice = useCostStore((s) => s.overview);
  const loadOverview = useCostStore((s) => s.loadOverview);
  const loadSignals = useCostStore((s) => s.loadSignals);
  const signalsSlice = useCostStore((s) => s.signals);
  const refresh = useCostStore((s) => s.refreshActive);
  const filtersKey = useCostStore((s) => s.filtersKey);

  useEffect(() => {
    if (active) {
      void loadOverview();
      void loadSignals();
    }
  }, [active, loadOverview, loadSignals, filtersKey]);

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
        {(data) => (
          <OverviewContent
            data={data}
            snapshot={signalsSlice.status === 'ready' ? signalsSlice.data : undefined}
          />
        )}
      </SliceStateBoundary>
    </div>
  );
}

function OverviewContent({ data, snapshot }: { data: CostOverview; snapshot?: CostSignalsSnapshot }) {
  return (
    <>
      <AiSummaryBox kpis={data.kpis} byApp={data.spendByApp} snapshot={snapshot} />

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

function AiSummaryBox({
  kpis,
  byApp,
  snapshot,
}: {
  kpis: CostKpi;
  byApp: GroupedSpend[];
  snapshot?: CostSignalsSnapshot;
}) {
  const topApp = byApp[0];
  const derivedSignals: Signal[] = [];

  if (kpis.pricingFallbackCalls > 0) {
    derivedSignals.push({
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
    derivedSignals.push({
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
      derivedSignals.push({
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

  const useSnapshot = snapshot !== undefined && snapshot.signals.length > 0;
  const isEmpty = !useSnapshot && derivedSignals.length === 0;

  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--chip-brand-border)] bg-[var(--surface-brand-subtle)] p-5 shadow-[var(--shadow-md)]">
      <div className="mb-3.5 flex items-center gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-lg)] bg-[var(--interactive-primary)] shadow-[var(--shadow-sm)]">
          <Sparkles className="h-[18px] w-[18px] text-[var(--text-on-color)]" />
        </span>
        <div className="flex flex-col">
          <h3 className="text-[15px] font-semibold leading-tight text-[var(--text-primary)]">
            Signals to watch
          </h3>
          <span className="text-[11px] font-medium uppercase tracking-wide text-[var(--text-muted)]">AI summary</span>
        </div>
      </div>
      {isEmpty ? (
        <p className="text-[13px] leading-relaxed text-[var(--text-secondary)]">
          Nothing unusual &mdash; no unpriced rows, errors within norm, spend balanced across apps.
        </p>
      ) : useSnapshot ? (
        <>
          <ul className="space-y-2">
            {snapshot!.signals.map((sig, i) => (
              <li
                key={i}
                className="flex items-start gap-2.5 text-[13px] leading-relaxed text-[var(--text-secondary)]"
              >
                <span
                  className={cn(
                    'mt-[6px] h-1.5 w-1.5 shrink-0 rounded-full',
                    sig.severity === 'warning' && 'bg-[var(--color-warning)]',
                    (sig.severity === 'error' || sig.severity === 'critical') && 'bg-[var(--color-error)]',
                    sig.severity !== 'warning' && sig.severity !== 'error' && sig.severity !== 'critical' && 'bg-[var(--color-info)]',
                  )}
                />
                <span>
                  <span className="font-medium text-[var(--text-primary)]">{sig.title}</span>
                  {' — '}
                  {sig.detail}
                </span>
              </li>
            ))}
          </ul>
          {(snapshot!.generatedAt || snapshot!.model) && (
            <p className="mt-2 text-[11px] text-[var(--text-muted)]">
              {snapshot!.generatedAt && <>Generated {formatDateTime(snapshot!.generatedAt)}</>}
              {snapshot!.generatedAt && snapshot!.model && ' · '}
              {snapshot!.model}
            </p>
          )}
        </>
      ) : (
        <ul className="space-y-2">
          {derivedSignals.map((signal) => (
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
          height={300}
          legendPosition="right"
          // hideSliceLabels keeps the ring big and clean; legend + hover tooltip carry the detail
          hideSliceLabels
        />
      )}
    </Card>
  );
}
