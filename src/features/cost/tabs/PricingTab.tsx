import { useEffect, useMemo, useState } from 'react';
import { RefreshCw, Tag, Plus, DollarSign } from 'lucide-react';
import { Alert, Badge, Button, DataTable, ProviderTag, Tabs, type ColumnDef } from '@/components/ui';
import { useCostStore } from '@/stores/costStore';
import { ApiError } from '@/services/api/client';
import { usePermission } from '@/utils/permissions';
import { notificationService } from '@/services/notifications';
import { SliceStateBoundary } from '../components/SliceStateBoundary';
import { CostSearchInput } from '../components/CostSearchInput';
import { formatDateTime, formatInt, formatUsd } from '../utils/format';
import type { PricingRow, RefreshDiff, SnapshotRow } from '../types';
import { PricingEditOverlay } from '../components/PricingEditOverlay';
import { RefreshDiffDialog } from '../components/RefreshDiffDialog';

interface TabProps {
  active: boolean;
}

type SubTab = 'rows' | 'history';

export function PricingTab({ active }: TabProps) {
  const slice = useCostStore((s) => s.pricing);
  const loadPricing = useCostStore((s) => s.loadPricing);
  const refresh = useCostStore((s) => s.refreshActive);
  const refreshFromModelsDev = useCostStore((s) => s.refreshFromModelsDev);
  const backfillUnpricedUsage = useCostStore((s) => s.backfillUnpricedUsage);
  const canEdit = usePermission('cost:manage');

  const [editing, setEditing] = useState<PricingRow | 'new' | null>(null);
  const [refreshBusy, setRefreshBusy] = useState(false);
  const [backfillBusy, setBackfillBusy] = useState(false);
  const [lastDiff, setLastDiff] = useState<RefreshDiff | null>(null);

  useEffect(() => {
    if (active) void loadPricing();
  }, [active, loadPricing]);

  const doRefresh = async () => {
    if (!canEdit) return;
    setRefreshBusy(true);
    try {
      const diff = await refreshFromModelsDev();
      setLastDiff(diff);
      await loadPricing();
    } catch (e) {
      if (e instanceof ApiError && e.status === 429) {
        const retryAfterRaw = e.headers?.get('retry-after');
        const retryAfter = retryAfterRaw ? Number(retryAfterRaw) : NaN;
        let wait = 'a moment';
        if (Number.isFinite(retryAfter) && retryAfter > 0) {
          wait =
            retryAfter >= 60
              ? `${Math.ceil(retryAfter / 60)} minute${Math.ceil(retryAfter / 60) === 1 ? '' : 's'}`
              : `${Math.ceil(retryAfter)} second${Math.ceil(retryAfter) === 1 ? '' : 's'}`;
        }
        notificationService.warning(`Pricing refresh is rate-limited. Try again in ${wait}.`);
      } else {
        const msg = e instanceof Error ? e.message : 'Refresh failed';
        notificationService.error(msg);
      }
    } finally {
      setRefreshBusy(false);
    }
  };

  const doBackfill = async () => {
    if (!canEdit) return;
    setBackfillBusy(true);
    try {
      await backfillUnpricedUsage();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Backfill failed';
      notificationService.error(msg);
    } finally {
      setBackfillBusy(false);
    }
  };

  // Empty check must ignore the "active pricing" filter on the bundle —
  // when the backend seeds are missing and no refresh has run, both the
  // active pricing and refresh-history arrays are empty.
  const isBundleEmpty = (data: { pricing: PricingRow[]; refreshHistory: SnapshotRow[] }) =>
    data.pricing.length === 0 && data.refreshHistory.length === 0;

  return (
    <div className="flex h-full min-h-0 flex-col pb-6">
      <SliceStateBoundary
        slice={slice}
        onRetry={() => refresh('pricing')}
        emptyIcon={Tag}
        emptyTitle="No pricing rows"
        emptyDescription="Seed the DB or refresh from models.dev to populate pricing."
        isEmpty={isBundleEmpty}
      >
        {(data) => (
          <>
            <Alert variant="info" title="Effective-dated pricing" className="mb-3">
              Adding a new rate creates a new row with <code className="font-mono">effective_from</code>{' '}
              and sets <code className="font-mono">effective_to</code> on the prior row. Historical
              rows are never edited — past costs remain reproducible.
            </Alert>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="text-[12px] text-[var(--text-muted)]">
                Active pricing rows live-override bootstrap seed. Edits require the
                <code className="ml-1 font-mono">cost:manage</code> permission.
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  icon={Plus}
                  disabled={!canEdit}
                  title={canEdit ? 'Add a pricing row' : 'Requires cost:manage permission'}
                  onClick={() => setEditing('new')}
                >
                  New row
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  icon={DollarSign}
                  disabled={!canEdit || backfillBusy}
                  isLoading={backfillBusy}
                  title={
                    canEdit
                      ? 'Re-price historical usage rows whose original pricing was missing'
                      : 'Requires cost:manage permission'
                  }
                  onClick={doBackfill}
                >
                  Backfill unpriced usage
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  icon={RefreshCw}
                  disabled={!canEdit}
                  isLoading={refreshBusy}
                  title={canEdit ? 'Refresh from models.dev' : 'Requires cost:manage permission'}
                  onClick={doRefresh}
                >
                  Refresh from models.dev
                </Button>
              </div>
            </div>

            <Tabs
              tabs={[
                {
                  id: 'rows',
                  label: 'Pricing rows',
                  content: (
                    <div className="flex h-full min-h-0 flex-col">
                      <PricingRowsTable
                        rows={data.pricing}
                        canEdit={canEdit}
                        onEdit={(row) => setEditing(row)}
                      />
                    </div>
                  ),
                },
                {
                  id: 'history',
                  label: 'Refresh history',
                  content: (
                    <div className="flex h-full min-h-0 flex-col">
                      <RefreshHistoryTable rows={data.refreshHistory} />
                    </div>
                  ),
                },
              ] as { id: SubTab; label: string; content: React.ReactNode }[]}
              defaultTab="rows"
              fillHeight
            />
          </>
        )}
      </SliceStateBoundary>

      {editing && (
        <PricingEditOverlay
          mode={editing === 'new' ? 'create' : 'patch'}
          pricing={editing === 'new' ? undefined : editing}
          onClose={() => setEditing(null)}
        />
      )}
      {lastDiff && <RefreshDiffDialog diff={lastDiff} onClose={() => setLastDiff(null)} />}
    </div>
  );
}

function PricingRowsTable({
  rows,
  canEdit,
  onEdit,
}: {
  rows: PricingRow[];
  canEdit: boolean;
  onEdit: (row: PricingRow) => void;
}) {
  const [query, setQuery] = useState('');

  const filteredRows = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((row) => {
      const haystack = `${row.provider} ${row.model} ${row.source} ${row.notes ?? ''}`.toLowerCase();
      return haystack.includes(q);
    });
  }, [rows, query]);

  const columns: ColumnDef<PricingRow>[] = [
    {
      key: 'provider',
      header: 'Provider',
      width: 'w-32',
      render: (row) => <ProviderTag value={row.provider} />,
    },
    {
      key: 'model',
      header: 'Model',
      width: 'w-80',
      render: (row) => (
        <span className="truncate" title={row.model}>
          {row.model}
        </span>
      ),
    },
    {
      key: 'effective',
      header: 'Effective',
      width: 'w-48',
      cellClassName: 'whitespace-nowrap',
      render: (row) => {
        const from = row.effectiveFrom ? row.effectiveFrom.slice(0, 10) : '—';
        const to = row.effectiveTo ? row.effectiveTo.slice(0, 10) : 'now';
        const isFuture = row.effectiveFrom ? new Date(row.effectiveFrom) > new Date() : false;
        const isExpired = row.effectiveTo !== null;
        const colorClass = isFuture
          ? 'text-[var(--interactive-primary)]'
          : isExpired
            ? 'text-[var(--text-muted)] italic'
            : 'text-[var(--text-secondary)]';
        return (
          <span className={`font-mono text-[11.5px] ${colorClass}`}>
            {from} → {to}
          </span>
        );
      },
    },
    {
      key: 'input',
      header: 'Input $/1M',
      width: 'w-28',
      cellClassName: 'text-right tabular-nums',
      headerClassName: 'text-right',
      render: (row) => formatUsd(row.inputPer1MUsd),
    },
    {
      key: 'output',
      header: 'Output $/1M',
      width: 'w-28',
      cellClassName: 'text-right tabular-nums',
      headerClassName: 'text-right',
      render: (row) => formatUsd(row.outputPer1MUsd),
    },
    {
      key: 'cached',
      header: 'Cached $/1M',
      width: 'w-28',
      cellClassName: 'text-right tabular-nums text-[var(--text-secondary)]',
      headerClassName: 'text-right',
      render: (row) => formatUsd(row.cachedReadPer1MUsd),
    },
    {
      key: 'reasoning',
      header: 'Reasoning $/1M',
      width: 'w-32',
      cellClassName: 'text-right tabular-nums text-[var(--text-secondary)]',
      headerClassName: 'text-right',
      render: (row) => formatUsd(row.reasoningPer1MUsd),
    },
    {
      key: 'source',
      header: 'Source',
      width: 'w-28',
      render: (row) => (
        <Badge variant={row.source === 'manual' ? 'warning' : 'neutral'} size="sm">
          {row.source}
        </Badge>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      width: 'w-24',
      render: (row) => {
        const isFuture = row.effectiveFrom ? new Date(row.effectiveFrom) > new Date() : false;
        if (isFuture) return <Badge variant="info" size="sm">scheduled</Badge>;
        if (row.effectiveTo === null) return <Badge variant="success" size="sm">active</Badge>;
        return <Badge variant="neutral" size="sm">historical</Badge>;
      },
    },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <CostSearchInput
        value={query}
        onCommit={setQuery}
        debounceMs={0}
        placeholder="Search by provider, model, source, or notes (e.g. gpt-5.4, azure, manual)"
        countLabel={
          query
            ? `${filteredRows.length} of ${rows.length}`
            : `${rows.length} row${rows.length === 1 ? '' : 's'}`
        }
      />
      <DataTable
        columns={columns}
        data={filteredRows}
        keyExtractor={(row) => row.id}
        emptyIcon={Tag}
        emptyTitle={query ? 'No matches' : 'No pricing rows'}
        emptyDescription={
          query
            ? `No pricing rows match "${query}". Clear the search to see all ${rows.length}.`
            : 'Seed the DB or refresh from models.dev to populate pricing.'
        }
        onRowClick={(row) => {
          if (!canEdit) {
            notificationService.info('Pricing edits require the cost:manage permission.');
            return;
          }
          if (row.effectiveTo !== null) {
            notificationService.info('This is a historical row; create a new row to update pricing.');
            return;
          }
          onEdit(row);
        }}
      />
    </div>
  );
}

function RefreshHistoryTable({ rows }: { rows: SnapshotRow[] }) {
  const columns: ColumnDef<SnapshotRow>[] = [
    {
      key: 'fetched_at',
      header: 'Fetched',
      width: 'w-40',
      render: (row) => formatDateTime(row.fetchedAt),
    },
    {
      key: 'status',
      header: 'Status',
      width: 'w-24',
      render: (row) => (
        <Badge variant={row.status === 'ok' ? 'success' : 'error'} size="sm">
          {row.status}
        </Badge>
      ),
    },
    {
      key: 'diff',
      header: 'Diff',
      render: (row) => (
        <span className="tabular-nums text-[var(--text-secondary)]">
          +{formatInt(row.addedCount)} / ~{formatInt(row.updatedCount)} / -{formatInt(row.removedCount)}{' '}
          <span className="text-[var(--text-muted)]">({formatInt(row.unchangedCount)} unchanged)</span>
        </span>
      ),
    },
    {
      key: 'duration',
      header: 'Duration',
      width: 'w-24',
      cellClassName: 'text-[var(--text-secondary)]',
      render: (row) => (row.durationMs != null ? `${row.durationMs} ms` : '—'),
    },
    {
      key: 'hash',
      header: 'Hash',
      width: 'w-40',
      cellClassName: 'font-mono text-[length:var(--text-table-header)] text-[var(--text-muted)]',
      render: (row) => row.payloadHash.slice(0, 12),
    },
  ];

  return (
    <DataTable
      columns={columns}
      data={rows}
      keyExtractor={(row) => row.id}
      emptyIcon={RefreshCw}
      emptyTitle="No snapshots"
      emptyDescription="No models.dev refreshes have run yet."
    />
  );
}
