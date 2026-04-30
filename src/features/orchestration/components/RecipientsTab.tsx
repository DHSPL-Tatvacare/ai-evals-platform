import { useCallback, useEffect, useState } from 'react';

import { DataTable, type ColumnDef } from '@/components/ui/DataTable';
import { listRunRecipients } from '@/services/api/orchestration';
import type { RecipientState } from '@/features/orchestration/types';
import { OverrideMenu } from './OverrideMenu';

const PAGE_SIZE = 50;

function fmtDate(s: string | null): string {
  if (!s) return '—';
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleString();
}

export function RecipientsTab({ runId }: { runId: string }) {
  const [rows, setRows] = useState<RecipientState[]>([]);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listRunRecipients(runId, {
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      });
      setRows(data);
    } finally {
      setLoading(false);
    }
  }, [runId, page]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const columns: ColumnDef<RecipientState>[] = [
    {
      key: 'recipientId',
      header: 'Recipient',
      render: (r) => (
        <span className="font-mono text-xs text-[var(--text-primary)]">{r.recipientId}</span>
      ),
    },
    {
      key: 'currentNodeId',
      header: 'Current Node',
      render: (r) => r.currentNodeId ?? '—',
    },
    {
      key: 'status',
      header: 'Status',
      render: (r) => (
        <span className="text-[var(--text-primary)]">{r.status}</span>
      ),
    },
    {
      key: 'enrolledAt',
      header: 'Enrolled',
      render: (r) => fmtDate(r.enrolledAt),
    },
    {
      key: 'wakeupAt',
      header: 'Wake-up',
      render: (r) => fmtDate(r.wakeupAt),
    },
    {
      key: '_override',
      header: '',
      width: '48px',
      render: (r) => (
        <OverrideMenu runId={runId} recipientId={r.recipientId} onApplied={refresh} />
      ),
    },
  ];

  // Page size is fixed at 50 here; total page count is unknown from this API
  // (no count returned), so we infer "there might be a next page" when the
  // current page is full. Bumping the page advances; bumping back is allowed.
  const hasMaybeMore = rows.length === PAGE_SIZE;
  const totalPages = hasMaybeMore ? page + 1 : page;

  return (
    <div className="p-3">
      <DataTable
        data={rows}
        columns={columns}
        keyExtractor={(r) => r.recipientId}
        loading={loading}
        emptyTitle="No recipients yet"
        emptyDescription="Recipients appear once the source node materialises the cohort."
        pagination={{
          page,
          totalPages,
          onPageChange: setPage,
          pageSize: PAGE_SIZE,
        }}
      />
    </div>
  );
}
