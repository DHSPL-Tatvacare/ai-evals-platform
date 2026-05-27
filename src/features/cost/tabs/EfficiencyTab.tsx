import { useEffect } from 'react';
import { Gauge } from 'lucide-react';
import { Card, DataTable, HBarList, ProviderTag, RingGauge, type ColumnDef, type HBarRowData } from '@/components/ui';
import { useCostStore } from '@/stores/costStore';
import { SliceStateBoundary } from '../components/SliceStateBoundary';
import { formatInt, formatTokensCompact, formatUsd, formatPercent } from '../utils/format';
import { toneForErrorCode, toneForPurpose } from '../utils/tones';
import type { EfficiencyBundle, EfficiencyGaugePoint, GroupedSpend } from '../types';

interface TabProps {
  active: boolean;
}

export function EfficiencyTab({ active }: TabProps) {
  const slice = useCostStore((s) => s.efficiency);
  const loadEfficiency = useCostStore((s) => s.loadEfficiency);
  const refresh = useCostStore((s) => s.refreshActive);
  const filtersKey = useCostStore((s) => s.filtersKey);

  useEffect(() => {
    if (active) void loadEfficiency();
  }, [active, loadEfficiency, filtersKey]);

  return (
    <div className="flex h-full min-h-0 flex-col space-y-4 pb-6">
      <SliceStateBoundary
        slice={slice}
        onRetry={() => refresh('efficiency')}
        emptyIcon={Gauge}
        emptyTitle="No efficiency data"
        emptyDescription="Cache, error, and unpriced metrics need at least one LLM request in range."
        isEmpty={(data) =>
          data.cacheByPurpose.length === 0 &&
          data.errorByCode.length === 0 &&
          data.unpricedCalls.length === 0 &&
          data.reasoningByModel.length === 0 &&
          pickValue(data.cacheGauge, 'cached_read') === 0 &&
          pickValue(data.errorGauge, 'errors') === 0
        }
      >
        {(data) => <EfficiencyContent data={data} />}
      </SliceStateBoundary>
    </div>
  );
}

function EfficiencyContent({ data }: { data: EfficiencyBundle }) {
  const hitRate = pickValue(data.cacheGauge, 'hit_rate');
  const cachedRead = pickValue(data.cacheGauge, 'cached_read');
  const errorRate = pickValue(data.errorGauge, 'error_rate');
  const errorCount = pickValue(data.errorGauge, 'errors');

  return (
    <>
      <div className="grid gap-4 lg:grid-cols-2">
        <CacheEfficiencyCard hitRate={hitRate} cachedTokens={cachedRead} rows={data.cacheByPurpose} />
        <ErrorHealthCard errorRate={errorRate} errorCount={errorCount} rows={data.errorByCode} />
      </div>

      <UnpricedCallsCard rows={data.unpricedCalls} />

      <ReasoningTokensCard rows={data.reasoningByModel} />
    </>
  );
}

function CacheEfficiencyCard({
  hitRate,
  cachedTokens,
  rows,
}: {
  hitRate: number;
  cachedTokens: number;
  rows: GroupedSpend[];
}) {
  const maxTokens = maxBy(rows, (r) => r.tokens);
  const hbarRows: HBarRowData[] = rows.slice(0, 6).map((row, i) => ({
    key: row.key,
    label: row.key,
    pct: maxTokens ? row.tokens / maxTokens : 0,
    tone: toneForPurpose(i),
    amount: formatTokensCompact(row.tokens),
    meta: row.costUsd > 0 ? formatUsd(row.costUsd) : undefined,
    metaTone: 'muted',
  }));
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">Cache efficiency</h3>
        <span className="text-[11.5px] text-[var(--text-muted)]">prompt caching</span>
      </div>
      <div className="flex items-center gap-4">
        <RingGauge value={hitRate} tone="accent" />
        <div>
          <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">Cache hit rate</p>
          <p className="mt-1 text-xl font-semibold tabular-nums text-[var(--text-primary)]">
            {formatPercent(hitRate)}
          </p>
          <p className="text-[11.5px] text-[var(--text-muted)]">
            {formatTokensCompact(cachedTokens)} cached tokens
          </p>
        </div>
      </div>
      <div className="mt-4">
        <p className="mb-2 text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
          Top purposes by tokens
        </p>
        <HBarList rows={hbarRows} />
      </div>
    </Card>
  );
}

function ErrorHealthCard({
  errorRate,
  errorCount,
  rows,
}: {
  errorRate: number;
  errorCount: number;
  rows: GroupedSpend[];
}) {
  const totalCalls = rows.reduce((sum, r) => sum + r.calls, 0);
  const maxCalls = maxBy(rows, (r) => r.calls);
  const hbarRows: HBarRowData[] = rows.map((row) => ({
    key: row.key,
    label: row.key,
    pct: maxCalls ? row.calls / maxCalls : 0,
    tone: toneForErrorCode(row.key),
    amount: formatInt(row.calls),
    meta: totalCalls ? `${((row.calls / totalCalls) * 100).toFixed(0)}%` : undefined,
    metaTone: 'muted',
  }));
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">Error &amp; health</h3>
        <span className="text-[11.5px] text-[var(--text-muted)]">in range</span>
      </div>
      <div className="flex items-center gap-4">
        <RingGauge
          value={errorRate}
          tone={errorRate > 0.01 ? 'error' : 'success'}
          centerLabel={formatPercent(errorRate, 1)}
        />
        <div>
          <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">Error rate</p>
          <p className="mt-1 text-xl font-semibold tabular-nums text-[var(--text-primary)]">
            {formatInt(errorCount)}
          </p>
          <p className="text-[11.5px] text-[var(--text-muted)]">failed requests</p>
        </div>
      </div>
      <div className="mt-4">
        <HBarList rows={hbarRows} />
      </div>
    </Card>
  );
}

function UnpricedCallsCard({ rows }: { rows: GroupedSpend[] }) {
  const columns: ColumnDef<GroupedSpend>[] = [
    {
      key: 'model',
      header: 'Model',
      render: (row) => (
        <span className="font-mono" title={row.key}>
          {row.key}
        </span>
      ),
    },
    {
      key: 'calls',
      header: 'API Requests',
      width: 'w-24',
      cellClassName: 'text-right tabular-nums',
      headerClassName: 'text-right',
      render: (row) => formatInt(row.calls),
    },
    {
      key: 'tokens',
      header: 'Tokens (billable)',
      width: 'w-40',
      cellClassName: 'text-right tabular-nums text-[var(--text-secondary)]',
      headerClassName: 'text-right',
      render: (row) => formatTokensCompact(row.tokens),
    },
  ];
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">Unpriced requests</h3>
        <span className="text-[11.5px] text-[var(--text-muted)]">needs a pricing row</span>
      </div>
      {rows.length === 0 ? (
        <p className="py-6 text-center text-xs text-[var(--text-muted)]">
          Every request in this range has a pricing row. Nothing to backfill.
        </p>
      ) : (
        <DataTable columns={columns} data={rows} keyExtractor={(row) => row.key} minWidth="0" />
      )}
    </Card>
  );
}

function ReasoningTokensCard({ rows }: { rows: GroupedSpend[] }) {
  const maxTokens = maxBy(rows, (r) => r.tokens);
  const hbarRows: HBarRowData[] = rows.map((row) => ({
    key: row.key,
    label: (
      <span className="inline-flex items-center gap-2">
        <ProviderTag value={providerOf(row.key)} withDot />
        <span className="font-mono text-[12px]">{row.key}</span>
      </span>
    ),
    pct: maxTokens ? row.tokens / maxTokens : 0,
    tone: 'purpose:purple-light',
    amount: `${formatTokensCompact(row.tokens)} tok`,
    meta: formatUsd(row.costUsd),
    metaTone: 'neutral',
  }));
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">Reasoning tokens</h3>
        <span className="text-[11.5px] text-[var(--text-muted)]">thinking-model spend</span>
      </div>
      {rows.length === 0 ? (
        <p className="py-6 text-center text-xs text-[var(--text-muted)]">
          No requests with reasoning tokens in range.
        </p>
      ) : (
        <HBarList
          rows={hbarRows}
          columnsTemplate="minmax(0, 1.2fr) minmax(0, 2fr) minmax(10ch, auto) minmax(7ch, auto)"
        />
      )}
    </Card>
  );
}

function pickValue(points: EfficiencyGaugePoint[], label: string): number {
  return points.find((p) => p.label === label)?.value ?? 0;
}

function maxBy<T>(rows: T[], fn: (row: T) => number): number {
  return rows.reduce((acc, r) => Math.max(acc, fn(r)), 0);
}

function providerOf(model: string): string {
  const lower = model.toLowerCase();
  if (lower.includes('claude')) return 'anthropic';
  if (lower.includes('gemini')) return 'gemini';
  if (lower.includes('gpt') || lower.includes('o1') || lower.includes('o3')) return 'openai';
  return '—';
}
