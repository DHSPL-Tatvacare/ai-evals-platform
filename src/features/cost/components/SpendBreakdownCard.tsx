import { type ReactNode, useMemo, useState } from 'react';
import { PieChart } from 'lucide-react';
import { Card, DataTable, PageHeaderSearch, type ColumnDef } from '@/components/ui';
import { cn } from '@/utils';
import { formatInt, formatTokensCompact, formatUsd } from '../utils/format';
import type { GroupedSpend } from '../types';

interface SpendBreakdownCardProps {
  title: string;
  subtitle?: string;
  rows: GroupedSpend[];
  nameHeader: string;
  renderName: (row: GroupedSpend) => ReactNode;
  searchPlaceholder: string;
}

export function SpendBreakdownCard({
  title,
  subtitle,
  rows,
  nameHeader,
  renderName,
  searchPlaceholder,
}: SpendBreakdownCardProps) {
  const [query, setQuery] = useState('');

  // Totals derive from the FULL row set so the proportional bars stay stable while searching.
  const { total, maxCost } = useMemo(() => {
    let t = 0;
    let m = 0;
    for (const r of rows) {
      t += r.costUsd;
      if (r.costUsd > m) m = r.costUsd;
    }
    return { total: t, maxCost: m };
  }, [rows]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) => r.key.toLowerCase().includes(q));
  }, [rows, query]);

  const columns: ColumnDef<GroupedSpend>[] = [
    {
      key: 'name',
      header: nameHeader,
      textBehavior: 'truncate',
      render: (row) => renderName(row),
    },
    {
      key: 'share',
      header: 'Share',
      width: 'w-44',
      render: (row) => {
        const fillPct = maxCost ? (row.costUsd / maxCost) * 100 : 0;
        const sharePct = total ? (row.costUsd / total) * 100 : 0;
        // Fixed-width track (not flex) so the bar is equally visible on every card,
        // even when a wide name column squeezes the row; min nub keeps tiny shares legible.
        return (
          <span className="flex items-center gap-2">
            <span className="h-2 w-24 shrink-0 overflow-hidden rounded-full bg-[var(--bg-tertiary)]">
              <span
                className="block h-full rounded-full bg-[var(--interactive-primary)]"
                style={{ width: `${fillPct > 0 ? Math.max(fillPct, 4) : 0}%` }}
              />
            </span>
            <span className="shrink-0 text-[11px] tabular-nums text-[var(--text-muted)]">
              {sharePct.toFixed(1)}%
            </span>
          </span>
        );
      },
    },
    {
      key: 'calls',
      header: 'API Requests',
      width: 'w-24',
      cellClassName: 'text-right tabular-nums text-[var(--text-secondary)]',
      headerClassName: 'text-right',
      render: (row) => formatInt(row.calls),
    },
    {
      key: 'tokens',
      header: 'Tokens',
      width: 'w-20',
      cellClassName: 'text-right tabular-nums text-[var(--text-secondary)]',
      headerClassName: 'text-right',
      render: (row) => formatTokensCompact(row.tokens),
    },
    {
      key: 'avg',
      header: 'Avg/req',
      width: 'w-20',
      cellClassName: 'text-right tabular-nums text-[var(--text-secondary)]',
      headerClassName: 'text-right',
      render: (row) => (row.calls ? formatUsd(row.costUsd / row.calls) : '—'),
    },
    {
      key: 'cost',
      header: 'Cost',
      width: 'w-24',
      cellClassName: 'text-right tabular-nums font-semibold',
      headerClassName: 'text-right',
      render: (row) => formatUsd(row.costUsd),
    },
  ];

  return (
    <Card className={cn('flex h-full min-h-0 flex-col p-4')}>
      <div className="mb-3 flex shrink-0 items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
        <div className="flex items-center gap-2">
          {subtitle && <span className="text-[11.5px] text-[var(--text-muted)]">{subtitle}</span>}
          <PageHeaderSearch
            value={query}
            onChange={setQuery}
            placeholder={searchPlaceholder}
            label={searchPlaceholder}
          />
        </div>
      </div>
      <div className="flex min-h-0 flex-1 flex-col">
        <DataTable
          columns={columns}
          data={filtered}
          keyExtractor={(row) => row.key}
          minWidth="0"
          emptyIcon={PieChart}
          emptyTitle="No spend recorded"
          emptyDescription="No spend matched the current range or search."
        />
      </div>
    </Card>
  );
}
