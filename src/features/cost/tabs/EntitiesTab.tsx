import { useCallback, useEffect } from 'react';
import { Database } from 'lucide-react';
import {
  Card,
  DataTable,
  HBarList,
  type ColumnDef,
  type HBarRowData,
} from '@/components/ui';
import { useCostStore } from '@/stores/costStore';
import { SliceStateBoundary } from '../components/SliceStateBoundary';
import { CostSearchInput } from '../components/CostSearchInput';
import { formatDateTime, formatInt, formatTokensCompact, formatUsd, truncateId } from '../utils/format';
import { toneForPurpose } from '../utils/tones';
import type { EntityCostBreakdown, EntityRow, GroupedSpend, OwnerType } from '../types';

interface TabProps {
  active: boolean;
}

const PAGE_SIZE = 25;

const OWNER_LABEL: Record<string, string> = {
  sherlock_turn: 'sherlock turn',
  eval_run: 'eval run',
  report_run: 'report',
  job: 'job',
  standalone: 'standalone',
};

export function EntitiesTab({ active }: TabProps) {
  const slice = useCostStore((s) => s.entities);
  const searchQuery = useCostStore((s) => s.entities.searchQuery);
  const loadEntities = useCostStore((s) => s.loadEntities);
  const setEntitiesSearch = useCostStore((s) => s.setEntitiesSearch);
  const refresh = useCostStore((s) => s.refreshActive);
  const filtersKey = useCostStore((s) => s.filtersKey);

  useEffect(() => {
    if (active) void loadEntities();
  }, [active, loadEntities, filtersKey]);

  const handleSearchCommit = useCallback((q: string) => setEntitiesSearch(q), [setEntitiesSearch]);

  const total = slice.status === 'ready' && slice.data ? slice.data.total : undefined;
  const countLabel =
    total !== undefined
      ? searchQuery
        ? `${total} match${total === 1 ? '' : 'es'}`
        : `${total} owner${total === 1 ? '' : 's'}`
      : undefined;

  return (
    <div className="flex h-full min-h-0 flex-col gap-2 pb-6">
      <CostSearchInput
        value={searchQuery}
        onCommit={handleSearchCommit}
        placeholder="Search by owner type, id, app, provider, model, or purpose (e.g. kaira, gpt-5.4, eval_run)"
        countLabel={countLabel}
      />
      <SliceStateBoundary
        slice={slice}
        onRetry={() => refresh('entities')}
        emptyIcon={Database}
        emptyTitle={searchQuery ? 'No matches' : 'No entities'}
        emptyDescription={
          searchQuery
            ? `No entities match "${searchQuery}". Clear the search to see all entities.`
            : 'No LLM usage rows match the current filters.'
        }
        isEmpty={(data) => data.items.length === 0}
      >
        {(data) => (
          <EntitiesTable
            rows={data.items}
            page={data.page}
            total={data.total}
            pageSize={data.pageSize || PAGE_SIZE}
            onPageChange={(p) => loadEntities(p)}
          />
        )}
      </SliceStateBoundary>
    </div>
  );
}

function EntitiesTable({
  rows,
  page,
  total,
  pageSize,
  onPageChange,
}: {
  rows: EntityRow[];
  page: number;
  total: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}) {
  const columns: ColumnDef<EntityRow>[] = [
    {
      key: 'owner',
      header: 'Owner',
      render: (row) => (
        <div className="flex min-w-0 items-center gap-2">
          <span className="inline-flex shrink-0 items-center rounded-[4px] bg-[var(--bg-tertiary)] px-1.5 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]">
            {OWNER_LABEL[row.ownerType] ?? row.ownerType}
          </span>
          <div className="flex min-w-0 flex-col">
            <span
              className="truncate text-[12.5px] text-[var(--text-primary)]"
              title={row.displayName ?? undefined}
            >
              {row.displayName ?? (
                <span className="font-mono text-[var(--text-secondary)]">{truncateId(row.ownerId)}</span>
              )}
            </span>
            {row.displayName && row.ownerId && (
              <span className="truncate font-mono text-[10.5px] text-[var(--text-muted)]" title={row.ownerId}>
                {truncateId(row.ownerId)}
              </span>
            )}
          </div>
        </div>
      ),
    },
    {
      key: 'cost',
      header: 'Spend',
      width: 'w-28',
      cellClassName: 'text-right tabular-nums font-semibold',
      headerClassName: 'text-right',
      render: (row) => formatUsd(row.costUsd),
    },
    {
      key: 'tokens',
      header: 'Tokens',
      width: 'w-24',
      cellClassName: 'text-right tabular-nums text-[var(--text-secondary)]',
      headerClassName: 'text-right',
      render: (row) => formatTokensCompact(row.totalTokens),
    },
    {
      key: 'calls',
      header: 'Calls',
      width: 'w-20',
      cellClassName: 'text-right tabular-nums text-[var(--text-secondary)]',
      headerClassName: 'text-right',
      render: (row) => formatInt(row.callCount),
    },
    {
      key: 'first_at',
      header: 'First call',
      width: 'w-40',
      cellClassName: 'whitespace-nowrap text-[var(--text-secondary)]',
      render: (row) => formatDateTime(row.firstAt),
    },
    {
      key: 'last_at',
      header: 'Last call',
      width: 'w-40',
      cellClassName: 'whitespace-nowrap text-[var(--text-secondary)]',
      render: (row) => formatDateTime(row.lastAt),
    },
  ];

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <DataTable
      columns={columns}
      data={rows}
      keyExtractor={(row) => `${row.ownerType}:${row.ownerId ?? 'null'}`}
      emptyIcon={Database}
      emptyTitle="No entities"
      emptyDescription="No LLM usage rows match the current filters."
      renderExpandedRow={(row) =>
        row.ownerId ? <EntityDrillDown ownerType={row.ownerType} ownerId={row.ownerId} /> : null
      }
      pagination={{
        page,
        totalPages,
        onPageChange,
        pageSize,
        totalItems: total,
        showCount: true,
      }}
    />
  );
}

function EntityDrillDown({ ownerType, ownerId }: { ownerType: OwnerType; ownerId: string }) {
  const loadEntity = useCostStore((s) => s.loadEntity);
  const filtersKey = useCostStore((s) => s.filtersKey);
  const detail = useCostStore(
    (s) => s.entityCache[`${filtersKey}:${ownerType}:${ownerId}`],
  );

  useEffect(() => {
    if (detail) return;
    void loadEntity(ownerType, ownerId);
  }, [loadEntity, ownerType, ownerId, detail]);

  if (!detail) {
    return <div className="py-2 text-xs text-[var(--text-muted)]">Loading drill-down…</div>;
  }
  return (
    <div className="space-y-4 py-2">
      <DrillSummary detail={detail} />
      <div className="grid gap-4 md:grid-cols-2">
        <DrillList title="By purpose" rows={detail.byPurpose} />
        <DrillList title="By model" rows={detail.byModel} />
      </div>
    </div>
  );
}

function DrillSummary({ detail }: { detail: EntityCostBreakdown }) {
  return (
    <Card className="p-3">
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-[12.5px]">
        <SummaryItem label="Spend" value={formatUsd(detail.costUsd)} highlight />
        <SummaryItem label="Tokens" value={formatTokensCompact(detail.totalTokens)} />
        <SummaryItem label="Calls" value={formatInt(detail.callCount)} />
        <SummaryItem label="Purposes" value={String(detail.byPurpose.length)} />
        <SummaryItem label="Models" value={String(detail.byModel.length)} />
      </div>
    </Card>
  );
}

function SummaryItem({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">{label}</span>
      <span
        className={`tabular-nums ${highlight ? 'font-semibold text-[var(--text-primary)]' : 'text-[var(--text-secondary)]'}`}
      >
        {value}
      </span>
    </div>
  );
}

function DrillList({ title, rows }: { title: string; rows: GroupedSpend[] }) {
  const total = rows.reduce((s, r) => s + r.costUsd, 0);
  const max = rows.reduce((m, r) => Math.max(m, r.costUsd), 0);
  const hbarRows: HBarRowData[] = rows.map((row, i) => ({
    key: row.key,
    label: row.key,
    pct: max ? row.costUsd / max : 0,
    tone: toneForPurpose(i),
    amount: formatUsd(row.costUsd),
    meta: total ? `${((row.costUsd / total) * 100).toFixed(0)}%` : undefined,
  }));
  return (
    <div>
      <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {title}
      </h4>
      {rows.length === 0 ? (
        <p className="py-2 text-xs text-[var(--text-muted)]">No data</p>
      ) : (
        <HBarList rows={hbarRows} />
      )}
    </div>
  );
}
