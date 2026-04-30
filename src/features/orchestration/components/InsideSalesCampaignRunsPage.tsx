import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { DataTable, type ColumnDef } from '@/components/ui/DataTable';
import { FilterPills } from '@/components/ui/FilterPills';
import { routes } from '@/config/routes';
import { listRuns, listWorkflows } from '@/services/api/orchestration';
import type { RunStatus, Workflow, WorkflowRun } from '@/features/orchestration/types';

const STATUS_FILTERS: { id: 'all' | RunStatus; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'running', label: 'Running' },
  { id: 'waiting', label: 'Waiting' },
  { id: 'completed', label: 'Completed' },
  { id: 'failed', label: 'Failed' },
  { id: 'cancelled', label: 'Cancelled' },
];

function fmtDate(s: string | null): string {
  if (!s) return '—';
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleString();
}

/** App-owned cross-campaign run log. Filters by status. Click row → run detail. */
export function InsideSalesCampaignRunsPage() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<WorkflowRun[]>([]);
  const [workflowsById, setWorkflowsById] = useState<Record<string, Workflow>>({});
  const [activeStatus, setActiveStatus] = useState<'all' | RunStatus>('all');
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [runs, workflows] = await Promise.all([
        listRuns({
          status: activeStatus === 'all' ? undefined : activeStatus,
          limit: 100,
        }),
        listWorkflows({ appId: 'inside-sales' }),
      ]);
      setRows(runs);
      const map: Record<string, Workflow> = {};
      for (const w of workflows) map[w.id] = w;
      setWorkflowsById(map);
    } finally {
      setLoading(false);
    }
  }, [activeStatus]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const columns: ColumnDef<WorkflowRun>[] = [
    {
      key: 'createdAt',
      header: 'Time',
      render: (r) => fmtDate(r.createdAt),
    },
    {
      key: 'workflow',
      header: 'Campaign',
      render: (r) => workflowsById[r.workflowId]?.name ?? r.workflowId.slice(0, 8),
    },
    {
      key: 'triggeredBy',
      header: 'Trigger',
      render: (r) => r.triggeredBy,
    },
    {
      key: 'status',
      header: 'Status',
      render: (r) => r.status,
    },
    {
      key: 'cohortSizeAtEntry',
      header: 'Cohort',
      render: (r) => r.cohortSizeAtEntry,
    },
    {
      key: 'completedAt',
      header: 'Completed',
      render: (r) => fmtDate(r.completedAt),
    },
  ];

  return (
    <div className="flex h-full flex-col p-4">
      <h1 className="mb-3 text-lg font-semibold text-[var(--text-primary)]">Campaign Runs</h1>
      <div className="mb-3">
        <FilterPills
          options={STATUS_FILTERS}
          active={activeStatus}
          onChange={(id) => setActiveStatus(id as 'all' | RunStatus)}
        />
      </div>
      <div className="min-h-0 flex-1">
        <DataTable
          data={rows}
          columns={columns}
          keyExtractor={(r) => r.id}
          loading={loading}
          emptyTitle="No campaign runs yet"
          emptyDescription="Trigger a campaign or wait for a scheduled run to fire."
          onRowClick={(r) => navigate(routes.insideSales.campaignRunDetail(r.id))}
        />
      </div>
    </div>
  );
}
