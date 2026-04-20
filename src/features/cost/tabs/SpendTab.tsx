import { useEffect } from 'react';
import { PieChart } from 'lucide-react';
import {
  Card,
  DataTable,
  HBarList,
  ProviderTag,
  type ColumnDef,
  type HBarRowData,
} from '@/components/ui';
import { useCostStore } from '@/stores/costStore';
import { SliceStateBoundary } from '../components/SliceStateBoundary';
import { formatInt, formatTokensCompact, formatUsd, truncateId } from '../utils/format';
import { toneForApp, toneForPurpose } from '../utils/tones';
import type { GroupedSpend, SpendBundle } from '../types';

interface TabProps {
  active: boolean;
}

export function SpendTab({ active }: TabProps) {
  const slice = useCostStore((s) => s.spend);
  const loadSpend = useCostStore((s) => s.loadSpend);
  const refresh = useCostStore((s) => s.refreshActive);
  const filtersKey = useCostStore((s) => s.filtersKey);

  useEffect(() => {
    if (active) void loadSpend();
  }, [active, loadSpend, filtersKey]);

  return (
    <div className="flex h-full min-h-0 flex-col space-y-4 pb-6">
      <SliceStateBoundary
        slice={slice}
        onRetry={() => refresh('spend')}
        emptyIcon={PieChart}
        emptyTitle="No spend"
        emptyDescription="No LLM spend was recorded for the selected range."
        isEmpty={(data) =>
          data.byApp.length === 0 &&
          data.byPurpose.length === 0 &&
          data.topModels.length === 0 &&
          data.topUsers.length === 0
        }
      >
        {(data) => <SpendContent data={data} />}
      </SliceStateBoundary>
    </div>
  );
}

function SpendContent({ data }: { data: SpendBundle }) {
  return (
    <>
      <div className="grid gap-4 lg:grid-cols-2">
        <ByAppCard rows={data.byApp} />
        <ByPurposeCard rows={data.byPurpose} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <TopModelsCard rows={data.topModels} />
        <TopUsersCard rows={data.topUsers} />
      </div>
    </>
  );
}

function ByAppCard({ rows }: { rows: GroupedSpend[] }) {
  const total = rows.reduce((s, r) => s + r.costUsd, 0);
  const max = rows.reduce((m, r) => Math.max(m, r.costUsd), 0);
  const hbarRows: HBarRowData[] = rows.map((row) => ({
    key: row.key,
    label: row.key,
    pct: max ? row.costUsd / max : 0,
    tone: toneForApp(row.key),
    amount: formatUsd(row.costUsd),
    meta: total ? `${((row.costUsd / total) * 100).toFixed(1)}%` : undefined,
  }));
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">By app</h3>
        <span className="text-[11.5px] text-[var(--text-muted)]">current range</span>
      </div>
      <HBarList rows={hbarRows} />
    </Card>
  );
}

function ByPurposeCard({ rows }: { rows: GroupedSpend[] }) {
  const total = rows.reduce((s, r) => s + r.costUsd, 0);
  const max = rows.reduce((m, r) => Math.max(m, r.costUsd), 0);
  const hbarRows: HBarRowData[] = rows.map((row, i) => ({
    key: row.key,
    label: row.key,
    pct: max ? row.costUsd / max : 0,
    tone: toneForPurpose(i),
    amount: formatUsd(row.costUsd),
    meta: total ? `${((row.costUsd / total) * 100).toFixed(1)}%` : undefined,
  }));
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">By call purpose</h3>
        <span className="text-[11.5px] text-[var(--text-muted)]">top {Math.min(rows.length, 8)}</span>
      </div>
      <HBarList rows={hbarRows} />
    </Card>
  );
}

function TopModelsCard({ rows }: { rows: GroupedSpend[] }) {
  const columns: ColumnDef<GroupedSpend>[] = [
    {
      key: 'provider',
      header: 'Provider',
      width: 'w-28',
      render: (row) => <ProviderTag value={providerOf(row.key)} />,
    },
    {
      key: 'model',
      header: 'Model',
      render: (row) => (
        <span className="font-mono text-[12px] text-[var(--text-primary)]" title={row.key}>
          {row.key}
        </span>
      ),
    },
    {
      key: 'calls',
      header: 'Calls',
      width: 'w-20',
      cellClassName: 'text-right tabular-nums text-[var(--text-secondary)]',
      headerClassName: 'text-right',
      render: (row) => formatInt(row.calls),
    },
    {
      key: 'tokens',
      header: 'Tokens',
      width: 'w-24',
      cellClassName: 'text-right tabular-nums text-[var(--text-secondary)]',
      headerClassName: 'text-right',
      render: (row) => formatTokensCompact(row.tokens),
    },
    {
      key: 'cost',
      header: 'Cost',
      width: 'w-28',
      cellClassName: 'text-right tabular-nums font-semibold',
      headerClassName: 'text-right',
      render: (row) => formatUsd(row.costUsd),
    },
  ];
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">Top models</h3>
        <span className="text-[11.5px] text-[var(--text-muted)]">by cost</span>
      </div>
      {rows.length === 0 ? (
        <p className="py-6 text-center text-xs text-[var(--text-muted)]">No spend recorded</p>
      ) : (
        <DataTable columns={columns} data={rows} keyExtractor={(row) => row.key} minWidth="0" />
      )}
    </Card>
  );
}

function TopUsersCard({ rows }: { rows: GroupedSpend[] }) {
  const columns: ColumnDef<GroupedSpend>[] = [
    {
      key: 'user',
      header: 'User',
      render: (row) => (
        <span className="font-mono text-[12px] text-[var(--text-primary)]" title={row.key}>
          {truncateId(row.key, 8)}
        </span>
      ),
    },
    {
      key: 'calls',
      header: 'Calls',
      width: 'w-24',
      cellClassName: 'text-right tabular-nums text-[var(--text-secondary)]',
      headerClassName: 'text-right',
      render: (row) => formatInt(row.calls),
    },
    {
      key: 'tokens',
      header: 'Tokens',
      width: 'w-24',
      cellClassName: 'text-right tabular-nums text-[var(--text-secondary)]',
      headerClassName: 'text-right',
      render: (row) => formatTokensCompact(row.tokens),
    },
    {
      key: 'cost',
      header: 'Cost',
      width: 'w-28',
      cellClassName: 'text-right tabular-nums font-semibold',
      headerClassName: 'text-right',
      render: (row) => formatUsd(row.costUsd),
    },
  ];
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">Top users</h3>
        <span className="text-[11.5px] text-[var(--text-muted)]">by cost</span>
      </div>
      {rows.length === 0 ? (
        <p className="py-6 text-center text-xs text-[var(--text-muted)]">No users in range</p>
      ) : (
        <DataTable columns={columns} data={rows} keyExtractor={(row) => row.key} minWidth="0" />
      )}
    </Card>
  );
}

function providerOf(model: string): string {
  const lower = model.toLowerCase();
  if (lower.includes('claude')) return 'anthropic';
  if (lower.includes('gemini')) return 'gemini';
  if (lower.includes('gpt') || lower.includes('o1') || lower.includes('o3')) return 'openai';
  return '—';
}
