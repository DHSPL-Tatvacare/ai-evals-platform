import { useCallback, useEffect, useState } from 'react';

import { DataTable, type ColumnDef } from '@/components/ui/DataTable';
import { listRunActions } from '@/services/api/orchestration';
import { isRunActive, type ActionRow, type RunStatus } from '@/features/orchestration/types';

const PAGE_SIZE = 100;
const ACTIVE_REFRESH_MS = 5000;

function fmtDate(s: string | null): string {
  if (!s) return '—';
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleString();
}

function detail(r: ActionRow): string {
  if (r.error) return r.error.slice(0, 80);
  if (!r.response) return '—';
  try {
    return JSON.stringify(r.response).slice(0, 80);
  } catch {
    return '—';
  }
}

export function ActionLogTab({ runId, runStatus }: { runId: string; runStatus: RunStatus }) {
  const [rows, setRows] = useState<ActionRow[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listRunActions(runId, { limit: PAGE_SIZE });
      setRows(data);
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!isRunActive(runStatus)) return;
    const interval = window.setInterval(() => {
      void refresh();
    }, ACTIVE_REFRESH_MS);
    return () => window.clearInterval(interval);
  }, [refresh, runStatus]);

  const columns: ColumnDef<ActionRow>[] = [
    {
      key: 'createdAt',
      header: 'Time',
      render: (r) => fmtDate(r.createdAt),
    },
    {
      key: 'recipientId',
      header: 'Recipient',
      render: (r) => (
        <span className="font-mono text-xs text-[var(--text-primary)]">{r.recipientId}</span>
      ),
    },
    {
      key: 'channel',
      header: 'Channel',
      render: (r) => r.channel,
    },
    {
      key: 'actionType',
      header: 'Action',
      render: (r) => r.actionType,
    },
    {
      key: 'status',
      header: 'Status',
      render: (r) => r.status,
    },
    {
      key: '_detail',
      header: 'Detail',
      render: (r) => (
        <span className="text-xs text-[var(--text-secondary)]">{detail(r)}</span>
      ),
    },
  ];

  return (
    <div className="p-3">
      <DataTable
        data={rows}
        columns={columns}
        keyExtractor={(r) => r.id}
        loading={loading}
        emptyTitle="No actions logged"
        emptyDescription="Actions appear as nodes dispatch them."
      />
    </div>
  );
}
