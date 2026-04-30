import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Button } from '@/components/ui/Button';
import { DataTable, type ColumnDef } from '@/components/ui/DataTable';
import { FilterPills } from '@/components/ui/FilterPills';
import { routes } from '@/config/routes';
import type { Workflow, WorkflowType } from '@/features/orchestration/types';
import { ApiError } from '@/services/api/client';
import { listSystemWorkflows, listWorkflows } from '@/services/api/orchestration';
import { notificationService } from '@/services/notifications';
import { CloneSystemWorkflowDialog } from './CloneSystemWorkflowDialog';
import { CreateWorkflowDialog } from './CreateWorkflowDialog';

const APP_ID = 'inside-sales';

const FILTER_OPTIONS: Array<{ id: 'all' | WorkflowType; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'crm', label: 'CRM' },
  { id: 'clinical', label: 'Clinical' },
];

const tenantColumns: ColumnDef<Workflow>[] = [
  {
    key: 'name',
    header: 'Name',
    render: (r) => <span className="text-[var(--text-primary)]">{r.name}</span>,
  },
  {
    key: 'workflowType',
    header: 'Type',
    render: (r) => (
      <span className="text-[var(--text-secondary)] uppercase">{r.workflowType}</span>
    ),
  },
  {
    key: 'status',
    header: 'Status',
    render: (r) =>
      r.currentPublishedVersionId ? (
        <span className="text-[var(--color-success)]">Published</span>
      ) : (
        <span className="text-[var(--text-secondary)]">Draft</span>
      ),
  },
  {
    key: 'updatedAt',
    header: 'Updated',
    render: (r) => (
      <span className="text-[var(--text-secondary)]">
        {new Date(r.updatedAt).toLocaleString()}
      </span>
    ),
  },
];

const systemColumns = (
  onClone: (workflow: Workflow) => void,
): ColumnDef<Workflow>[] => [
  {
    key: 'name',
    header: 'Name',
    render: (workflow) => (
      <div className="flex flex-col gap-1">
        <span className="text-[var(--text-primary)]">{workflow.name}</span>
        {workflow.description ? (
          <span className="text-xs text-[var(--text-secondary)]">{workflow.description}</span>
        ) : null}
      </div>
    ),
  },
  {
    key: 'workflowType',
    header: 'Type',
    render: (workflow) => (
      <span className="text-[var(--text-secondary)] uppercase">{workflow.workflowType}</span>
    ),
  },
  {
    key: 'slug',
    header: 'Slug',
    render: (workflow) => (
      <span className="font-mono text-xs text-[var(--text-secondary)]">{workflow.slug}</span>
    ),
  },
  {
    key: 'updatedAt',
    header: 'Updated',
    render: (workflow) => (
      <span className="text-[var(--text-secondary)]">
        {new Date(workflow.updatedAt).toLocaleString()}
      </span>
    ),
  },
  {
    key: '_clone',
    header: '',
    width: '140px',
    render: (workflow) => (
      <Button
        size="sm"
        onClick={(event) => {
          event.stopPropagation();
          onClone(workflow);
        }}
      >
        Clone for Tenant
      </Button>
    ),
  },
];

export function WorkflowListPage() {
  const [tenantRows, setTenantRows] = useState<Workflow[]>([]);
  const [systemRows, setSystemRows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [activeType, setActiveType] = useState<'all' | WorkflowType>('all');
  const [cloneSource, setCloneSource] = useState<Workflow | null>(null);
  const navigate = useNavigate();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const workflowType = activeType === 'all' ? undefined : activeType;
      const [tenantWorkflows, systemWorkflows] = await Promise.all([
        listWorkflows({ appId: APP_ID, workflowType }),
        listSystemWorkflows({ appId: APP_ID, workflowType }),
      ]);
      setTenantRows(tenantWorkflows);
      setSystemRows(systemWorkflows);
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : 'Failed to load campaigns';
      notificationService.error(msg);
    } finally {
      setLoading(false);
    }
  }, [activeType]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-[var(--text-primary)]">Workflows</h1>
        <Button onClick={() => setShowCreate(true)}>New Workflow</Button>
      </div>
      <div className="mb-3">
        <FilterPills
          options={FILTER_OPTIONS}
          active={activeType}
          onChange={(id) => setActiveType(id as 'all' | WorkflowType)}
        />
      </div>
      <div className="flex flex-col gap-6">
        <section className="flex min-h-0 flex-1 flex-col gap-2">
          <div className="text-sm font-medium text-[var(--text-primary)]">Your Workflows</div>
          <DataTable<Workflow>
            data={tenantRows}
            columns={tenantColumns}
            keyExtractor={(workflow) => workflow.id}
            loading={loading}
            emptyTitle="No workflows yet"
            emptyDescription="Create a workflow to start designing an orchestration."
            onRowClick={(workflow) => navigate(routes.insideSales.campaignBuilder(workflow.id))}
          />
        </section>
        <section className="flex min-h-0 flex-1 flex-col gap-2">
          <div className="text-sm font-medium text-[var(--text-primary)]">System Starters</div>
          <DataTable<Workflow>
            data={systemRows}
            columns={systemColumns(setCloneSource)}
            keyExtractor={(workflow) => workflow.id}
            loading={loading}
            emptyTitle="No system workflows available"
            emptyDescription="System-seeded starter workflows appear here when available for your app."
          />
        </section>
      </div>
      {showCreate && (
        <CreateWorkflowDialog
          onClose={() => setShowCreate(false)}
          onCreated={(workflow) => {
            setShowCreate(false);
            navigate(routes.insideSales.campaignBuilder(workflow.id));
          }}
        />
      )}
      {cloneSource && (
        <CloneSystemWorkflowDialog
          sourceWorkflow={cloneSource}
          onClose={() => setCloneSource(null)}
          onCloned={(workflow) => {
            setCloneSource(null);
            void refresh();
            navigate(routes.insideSales.campaignBuilder(workflow.id));
          }}
        />
      )}
    </div>
  );
}
