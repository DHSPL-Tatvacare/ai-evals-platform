import { useCallback, useEffect, useState } from 'react';
import { Activity, X } from 'lucide-react';
import { AppTag, Badge, DataTable, ProviderTag, type ColumnDef } from '@/components/ui';
import { useCostStore } from '@/stores/costStore';
import { SliceStateBoundary } from '../components/SliceStateBoundary';
import { CostSearchInput } from '../components/CostSearchInput';
import { formatDateTime, formatInt, formatTokensCompact, formatUsd, truncateId } from '../utils/format';
import type { CallDetail, CallRow } from '../types';

interface TabProps {
  active: boolean;
}

export function CallsTab({ active }: TabProps) {
  const slice = useCostStore((s) => s.calls);
  const searchQuery = useCostStore((s) => s.calls.searchQuery);
  const loadCalls = useCostStore((s) => s.loadCalls);
  const setCallsSearch = useCostStore((s) => s.setCallsSearch);
  const refresh = useCostStore((s) => s.refreshActive);
  const filtersKey = useCostStore((s) => s.filtersKey);
  const loadCallDetail = useCostStore((s) => s.loadCallDetail);

  const [activeCall, setActiveCall] = useState<CallDetail | null>(null);

  useEffect(() => {
    if (active) void loadCalls();
  }, [active, loadCalls, filtersKey]);

  const openCall = async (id: string) => {
    const detail = await loadCallDetail(id);
    if (detail) setActiveCall(detail);
  };

  const handleSearchCommit = useCallback((q: string) => setCallsSearch(q), [setCallsSearch]);

  const total = slice.status === 'ready' && slice.data ? slice.data.total : undefined;
  const countLabel =
    total !== undefined
      ? searchQuery
        ? `${total} match${total === 1 ? '' : 'es'}`
        : `${total} call${total === 1 ? '' : 's'}`
      : undefined;

  return (
    <div className="flex h-full min-h-0 flex-col gap-2 pb-6">
      <CostSearchInput
        value={searchQuery}
        onCommit={handleSearchCommit}
        placeholder="Search by provider, model, app, purpose, or finish reason (e.g. kaira, gpt-5.4, efficiency)"
        countLabel={countLabel}
      />
      <SliceStateBoundary
        slice={slice}
        onRetry={() => refresh('calls')}
        emptyIcon={Activity}
        emptyTitle={searchQuery ? 'No matches' : 'No calls'}
        emptyDescription={
          searchQuery
            ? `No calls match "${searchQuery}". Clear the search to see all calls.`
            : 'No LLM calls match the current filters.'
        }
        isEmpty={(data) => data.items.length === 0}
      >
        {(data) => (
          <CallsTable
            rows={data.items}
            page={data.page}
            total={data.total}
            pageSize={data.pageSize}
            onPageChange={(p) => loadCalls(p)}
            onRowClick={(row) => openCall(row.id)}
          />
        )}
      </SliceStateBoundary>
      {activeCall && <CallDetailDrawer call={activeCall} onClose={() => setActiveCall(null)} />}
    </div>
  );
}

function CallsTable({
  rows,
  page,
  total,
  pageSize,
  onPageChange,
  onRowClick,
}: {
  rows: CallRow[];
  page: number;
  total: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onRowClick: (row: CallRow) => void;
}) {
  const columns: ColumnDef<CallRow>[] = [
    {
      key: 'created_at',
      header: 'When',
      width: 'w-40',
      render: (row) => (
        <span className="whitespace-nowrap font-mono text-[11.5px] text-[var(--text-secondary)]">
          {formatDateTime(row.createdAt)}
        </span>
      ),
    },
    {
      key: 'app',
      header: 'App',
      width: 'w-28',
      render: (row) => <AppTag value={row.appId} />,
    },
    {
      key: 'provider',
      header: 'Provider',
      width: 'w-28',
      render: (row) => <ProviderTag value={row.provider} />,
    },
    {
      key: 'model',
      header: 'Model',
      width: 'w-56',
      render: (row) => (
        <span className="truncate font-mono" title={row.model}>
          {row.model}
        </span>
      ),
    },
    {
      key: 'purpose',
      header: 'Purpose',
      width: 'w-36',
      render: (row) => (
        <span className="text-[var(--text-secondary)]">{row.callPurpose ?? '—'}</span>
      ),
    },
    {
      key: 'in',
      header: 'In',
      width: 'w-20',
      cellClassName: 'text-right tabular-nums text-[var(--text-secondary)]',
      headerClassName: 'text-right',
      render: (row) => formatTokensCompact(row.inputTokens),
    },
    {
      key: 'out',
      header: 'Out',
      width: 'w-20',
      cellClassName: 'text-right tabular-nums text-[var(--text-secondary)]',
      headerClassName: 'text-right',
      render: (row) => formatTokensCompact(row.outputTokens),
    },
    {
      key: 'cache',
      header: 'Cache R',
      width: 'w-20',
      cellClassName: 'text-right tabular-nums text-[var(--text-secondary)]',
      headerClassName: 'text-right',
      render: (row) =>
        row.cachedReadTokens > 0 ? formatTokensCompact(row.cachedReadTokens) : '—',
    },
    {
      key: 'reason',
      header: 'Reason',
      width: 'w-20',
      cellClassName: 'text-right tabular-nums text-[var(--text-secondary)]',
      headerClassName: 'text-right',
      render: (row) =>
        row.reasoningTokens > 0 ? formatTokensCompact(row.reasoningTokens) : '—',
    },
    {
      key: 'ms',
      header: 'ms',
      width: 'w-16',
      cellClassName: 'text-right tabular-nums text-[var(--text-secondary)]',
      headerClassName: 'text-right',
      render: (row) => (row.durationMs != null ? formatInt(row.durationMs) : '—'),
    },
    {
      key: 'status',
      header: 'Status',
      width: 'w-40',
      render: (row) => <StatusCell row={row} />,
    },
    {
      key: 'cost',
      header: 'Spend',
      width: 'w-24',
      cellClassName: 'text-right tabular-nums font-semibold',
      headerClassName: 'text-right',
      render: (row) => formatUsd(row.costUsd),
    },
  ];

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <DataTable
      columns={columns}
      data={rows}
      keyExtractor={(row) => row.id}
      onRowClick={onRowClick}
      emptyIcon={Activity}
      emptyTitle="No calls"
      emptyDescription="No LLM calls match the current filters."
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

function StatusCell({ row }: { row: CallRow }) {
  const cachePct =
    row.cachedReadTokens > 0 && row.inputTokens > 0
      ? Math.round((row.cachedReadTokens / row.inputTokens) * 100)
      : 0;
  return (
    <div className="flex flex-wrap items-center gap-1">
      <Badge variant={row.status === 'ok' ? 'success' : 'error'} size="sm">
        {row.status}
      </Badge>
      {cachePct >= 20 && (
        <span className="inline-flex items-center rounded-[4px] bg-[var(--surface-brand-subtle)] px-1.5 py-0.5 text-[10.5px] font-medium text-[var(--interactive-primary)]">
          cache {cachePct}%
        </span>
      )}
      {row.pricingFallback && (
        <span className="inline-flex items-center rounded-[4px] bg-[var(--surface-warning)] px-1.5 py-0.5 text-[10.5px] font-medium text-[var(--color-warning-dark)]">
          no rate
        </span>
      )}
    </div>
  );
}

function CallDetailDrawer({ call, onClose }: { call: CallDetail; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 flex justify-end"
      style={{ zIndex: 'var(--z-overlay)' } as React.CSSProperties}
    >
      <button
        type="button"
        aria-label="Close drawer"
        onClick={onClose}
        className="absolute inset-0 bg-[var(--bg-overlay)] backdrop-blur-sm"
      />
      <aside className="relative flex h-full w-full max-w-[560px] flex-col overflow-y-auto border-l border-[var(--border-default)] bg-[var(--bg-elevated)] p-5 shadow-lg">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-[var(--text-primary)]">Call detail</h2>
            <p className="mt-1 font-mono text-[11px] text-[var(--text-muted)]">{call.id}</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-[6px] p-1 text-[var(--text-muted)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-[13px]">
          <Field label="Provider" value={<ProviderTag value={call.provider} />} />
          <Field label="Model" value={call.model} />
          <Field label="App" value={<AppTag value={call.appId} />} />
          <Field label="Purpose" value={call.callPurpose ?? '—'} />
          <Field label="Status" value={<Badge variant={call.status === 'ok' ? 'success' : 'error'} size="sm">{call.status}</Badge>} />
          <Field label="Finish" value={call.finishReason ?? '—'} />
          <Field label="Duration" value={call.durationMs != null ? `${call.durationMs} ms` : '—'} />
          <Field label="Correlation" value={<code className="font-mono text-[11px]">{truncateId(call.correlationId)}</code>} />
          <Field label="Owner" value={`${call.ownerType} / ${truncateId(call.ownerId)}`} />
          <Field label="User" value={truncateId(call.userId)} />
        </dl>

        <div className="mt-5 space-y-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-3">
          <h3 className="text-[12px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">Token breakdown</h3>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[13px]">
            <span className="text-[var(--text-muted)]">Input</span>
            <span className="text-right tabular-nums">{formatInt(call.inputTokens)}</span>
            <span className="text-[var(--text-muted)]">Output</span>
            <span className="text-right tabular-nums">{formatInt(call.outputTokens)}</span>
            <span className="text-[var(--text-muted)]">Cached read</span>
            <span className="text-right tabular-nums">{formatInt(call.cachedReadTokens)}</span>
            <span className="text-[var(--text-muted)]">Reasoning</span>
            <span className="text-right tabular-nums">{formatInt(call.reasoningTokens)}</span>
            <span className="border-t border-[var(--border-subtle)] pt-1 font-semibold text-[var(--text-primary)]">Total</span>
            <span className="border-t border-[var(--border-subtle)] pt-1 text-right font-semibold tabular-nums text-[var(--text-primary)]">
              {formatInt(call.totalTokens)}
            </span>
          </div>
        </div>

        <div className="mt-4 flex items-center justify-between rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-[13px]">
          <span className="text-[var(--text-muted)]">Spend</span>
          <span className="tabular-nums text-lg font-semibold text-[var(--text-primary)]">
            {formatUsd(call.costUsd)}
          </span>
        </div>

        {call.pricingFallback && (
          <p className="mt-2 text-[11px] text-[var(--color-warning)]">
            ⚠ Priced with fallback — add a pricing row for {call.provider}/{call.model}.
          </p>
        )}

        {call.costBreakdown && (
          <BreakdownSection title="Cost breakdown" payload={call.costBreakdown} />
        )}
        {call.modalityDetails && (
          <BreakdownSection title="Modality detail" payload={call.modalityDetails} />
        )}
        {call.serverToolUsage && (
          <BreakdownSection title="Server tools" payload={call.serverToolUsage} />
        )}
      </aside>
    </div>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">{label}</dt>
      <dd className="mt-0.5 truncate text-[var(--text-primary)]">{value}</dd>
    </div>
  );
}

function BreakdownSection({ title, payload }: { title: string; payload: Record<string, unknown> }) {
  return (
    <details className="mt-4 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)]">
      <summary className="cursor-pointer select-none px-3 py-2 text-[12px] font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
        {title}
      </summary>
      <pre className="overflow-auto px-3 pb-3 text-[11px] text-[var(--text-secondary)]">
        {JSON.stringify(payload, null, 2)}
      </pre>
    </details>
  );
}
