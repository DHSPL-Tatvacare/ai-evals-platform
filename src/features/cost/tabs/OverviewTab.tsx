import { useEffect } from 'react';
import { BarChart3 } from 'lucide-react';
import { Alert, Card, HBarList, type HBarRowData } from '@/components/ui';
import { useCostStore } from '@/stores/costStore';
import { ChartRenderer } from '@/features/analytics/components/ChartRenderer';
import { CostKpiRow } from '../components/CostKpiRow';
import { SliceStateBoundary } from '../components/SliceStateBoundary';
import { formatInt, formatUsd, formatUsdCompact } from '../utils/format';
import { toneForApp, toneForPurpose } from '../utils/tones';
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
        emptyDescription="No LLM calls were recorded for the selected range."
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
        <WhereTheMoneyGoes byApp={data.spendByApp} byPurpose={data.spendByPurpose} />
        <SignalsCard kpis={data.kpis} byApp={data.spendByApp} />
      </div>
    </>
  );
}

function WhereTheMoneyGoes({ byApp, byPurpose }: { byApp: GroupedSpend[]; byPurpose: GroupedSpend[] }) {
  const totalApp = byApp.reduce((s, r) => s + r.costUsd, 0);
  const totalPurpose = byPurpose.reduce((s, r) => s + r.costUsd, 0);
  const maxApp = byApp.reduce((m, r) => Math.max(m, r.costUsd), 0);
  const maxPurpose = byPurpose.reduce((m, r) => Math.max(m, r.costUsd), 0);

  const appRows: HBarRowData[] = byApp.slice(0, 5).map((row) => ({
    key: `app:${row.key}`,
    label: row.key,
    pct: maxApp ? row.costUsd / maxApp : 0,
    tone: toneForApp(row.key),
    amount: formatUsd(row.costUsd),
    meta: totalApp ? `${((row.costUsd / totalApp) * 100).toFixed(0)}%` : undefined,
  }));
  const purposeRows: HBarRowData[] = byPurpose.slice(0, 6).map((row, i) => ({
    key: `purpose:${row.key}`,
    label: row.key,
    pct: maxPurpose ? row.costUsd / maxPurpose : 0,
    tone: toneForPurpose(i),
    amount: formatUsd(row.costUsd),
    meta: totalPurpose ? `${((row.costUsd / totalPurpose) * 100).toFixed(0)}%` : undefined,
  }));

  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">Where the money goes</h3>
        <span className="text-[11.5px] text-[var(--text-muted)]">top apps &amp; purposes</span>
      </div>
      {appRows.length === 0 && purposeRows.length === 0 ? (
        <p className="py-6 text-center text-xs text-[var(--text-muted)]">No spend recorded</p>
      ) : (
        <div className="space-y-4">
          {appRows.length > 0 && (
            <div>
              <p className="mb-2 text-[11px] uppercase tracking-wide text-[var(--text-muted)]">By app</p>
              <HBarList rows={appRows} />
            </div>
          )}
          {purposeRows.length > 0 && (
            <div>
              <p className="mb-2 text-[11px] uppercase tracking-wide text-[var(--text-muted)]">By purpose</p>
              <HBarList rows={purposeRows} />
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function SignalsCard({ kpis, byApp }: { kpis: CostKpi; byApp: GroupedSpend[] }) {
  const topApp = byApp[0];
  const signals: React.ReactNode[] = [];

  if (kpis.pricingFallbackCalls > 0) {
    signals.push(
      <Alert key="unpriced" variant="warning" title="Unpriced calls">
        <span className="tabular-nums">{formatInt(kpis.pricingFallbackCalls)}</span> calls were priced with
        a fallback rate. Add a pricing row to stop under-accounting for spend.
      </Alert>,
    );
  }
  if (kpis.errorCalls > 0) {
    const errorPct = kpis.totalCalls ? kpis.errorCalls / kpis.totalCalls : 0;
    signals.push(
      <Alert key="errors" variant={errorPct > 0.02 ? 'error' : 'info'} title="Call errors">
        <span className="tabular-nums">{formatInt(kpis.errorCalls)}</span> failed calls
        {kpis.totalCalls > 0 && (
          <> &middot; {(errorPct * 100).toFixed(2)}% of traffic</>
        )}
        .
      </Alert>,
    );
  }
  if (topApp && byApp.length > 1) {
    const total = byApp.reduce((s, r) => s + r.costUsd, 0);
    const share = total ? topApp.costUsd / total : 0;
    if (share >= 0.5) {
      signals.push(
        <Alert key="concentration" variant="info" title="Spend concentration">
          <span className="font-medium">{topApp.key}</span> drives {(share * 100).toFixed(0)}% of all spend
          ({formatUsdCompact(topApp.costUsd)}). Investigate its per-purpose breakdown in Spend.
        </Alert>,
      );
    }
  }

  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">Signals to watch</h3>
        <span className="text-[11.5px] text-[var(--text-muted)]">auto-curated</span>
      </div>
      {signals.length === 0 ? (
        <p className="py-6 text-center text-xs text-[var(--text-muted)]">
          Nothing unusual. No unpriced rows, errors within norm, spend balanced across apps.
        </p>
      ) : (
        <div className="space-y-2.5">{signals}</div>
      )}
    </Card>
  );
}
