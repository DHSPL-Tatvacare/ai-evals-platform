import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Archive, Copy, History, Pencil, Play } from 'lucide-react';
import { cn } from '@/utils/cn';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { DataTable, type ColumnDef } from '@/components/ui/DataTable';
import { FilterPills } from '@/components/ui/FilterPills';
import { IconButton } from '@/components/ui/IconButton';
import { PageSurface } from '@/components/ui/PageSurface';
import { usePageMetadata } from '@/config/pageMetadata';
import { useCurrentAppId } from '@/hooks';
import type { RunStatus, Workflow } from '@/features/orchestration/types';
import { useOrchestrationRoutes } from '@/features/orchestration/hooks/useOrchestrationRoutes';
import { ApiError } from '@/services/api/client';
import { formatDateTime } from '@/utils/formatters';
import { timeAgo } from '@/utils/evalFormatters';
import {
  archiveWorkflow,
  fireManualRun,
  listSystemWorkflows,
  listWorkflows,
} from '@/services/api/orchestration';
import { notificationService } from '@/services/notifications';
import { CloneSystemWorkflowDialog } from './CloneSystemWorkflowDialog';
import { CreateWorkflowDialog } from './CreateWorkflowDialog';
import { WorkflowRunHistoryOverlay } from './WorkflowRunHistoryOverlay';

type SourceFilter = 'all' | 'custom' | 'platform';

const SOURCE_FILTERS: Array<{ id: SourceFilter; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'custom', label: 'Custom' },
  { id: 'platform', label: 'Platform' },
];

interface UnifiedRow extends Workflow {
  source: 'custom' | 'platform';
}

/** Compact 11px inline chip — same shape as ScheduledJobsListPage's
 *  ``LastFireChip`` so list-page status pills read identical across
 *  surfaces. Uses design-system tokens (no hex literals). */
const RUN_STATUS_CHIP_CLASSES: Record<RunStatus, string> = {
  pending: 'bg-[var(--bg-tertiary)] text-[var(--text-muted)]',
  running: 'bg-[var(--surface-info)] text-[var(--color-info)]',
  waiting: 'bg-[var(--surface-warning)] text-[var(--color-warning)]',
  completed: 'bg-[var(--surface-success)] text-[var(--color-success)]',
  failed: 'bg-[var(--surface-error)] text-[var(--color-error)]',
  cancelled: 'bg-[var(--bg-tertiary)] text-[var(--text-muted)]',
};

function RunStatusChip({ status }: { status: RunStatus }) {
  return (
    <span
      className={cn(
        'inline-flex w-fit items-center rounded-full px-2 py-0.5 text-[11px] font-medium capitalize',
        RUN_STATUS_CHIP_CLASSES[status],
      )}
    >
      {status}
    </span>
  );
}

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return formatDateTime(d);
}

function fmtRelative(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return timeAgo(iso);
}

export function WorkflowListPage() {
  const { icon, title } = usePageMetadata('campaigns');
  const [tenantRows, setTenantRows] = useState<Workflow[]>([]);
  const [systemRows, setSystemRows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [activeSource, setActiveSource] = useState<SourceFilter>('all');
  const [cloneSource, setCloneSource] = useState<Workflow | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<Workflow | null>(null);
  const [historyTarget, setHistoryTarget] = useState<Workflow | null>(null);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [archivingId, setArchivingId] = useState<string | null>(null);
  const navigate = useNavigate();
  const appId = useCurrentAppId();
  const orchestrationRoutes = useOrchestrationRoutes();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [tenantWorkflows, systemWorkflows] = await Promise.all([
        listWorkflows({ appId }),
        listSystemWorkflows({ appId }),
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
  }, [appId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const allRows = useMemo<UnifiedRow[]>(() => {
    const merged: UnifiedRow[] = [
      ...tenantRows.map((w) => ({ ...w, source: 'custom' as const })),
      ...systemRows.map((w) => ({ ...w, source: 'platform' as const })),
    ];
    merged.sort(
      (a, b) =>
        new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
    );
    return merged;
  }, [tenantRows, systemRows]);

  const visibleRows = useMemo(() => {
    if (activeSource === 'all') return allRows;
    return allRows.filter((r) => r.source === activeSource);
  }, [allRows, activeSource]);

  const handleRun = useCallback(async (workflow: Workflow) => {
    setRunningId(workflow.id);
    try {
      const run = await fireManualRun(workflow.id);
      notificationService.success(`Run started: ${run.id.slice(0, 8)}`);
      navigate(orchestrationRoutes.campaignRunDetail(run.id));
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : 'Failed to start run';
      notificationService.error(msg);
    } finally {
      setRunningId(null);
    }
  }, [navigate, orchestrationRoutes]);

  const handleArchive = useCallback(async () => {
    if (!archiveTarget) return;
    setArchivingId(archiveTarget.id);
    try {
      await archiveWorkflow(archiveTarget.id);
      notificationService.success(`Archived "${archiveTarget.name}"`);
      setArchiveTarget(null);
      await refresh();
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : 'Failed to archive workflow';
      notificationService.error(msg);
    } finally {
      setArchivingId(null);
    }
  }, [archiveTarget, refresh]);

  const columns: ColumnDef<UnifiedRow>[] = [
    {
      key: 'name',
      header: 'Name',
      width: 'min-w-[260px] max-w-[420px]',
      render: (r) => (
        <div className="flex flex-col gap-0.5">
          <span className="truncate text-[var(--text-primary)]">{r.name}</span>
          {r.description ? (
            <span className="line-clamp-1 text-[length:var(--text-table-header)] text-[var(--text-secondary)]">
              {r.description}
            </span>
          ) : null}
        </div>
      ),
    },
    {
      key: 'source',
      header: 'Source',
      width: 'w-[110px]',
      render: (r) =>
        r.source === 'custom' ? (
          <Badge variant="success" size="sm">Custom</Badge>
        ) : (
          <Badge variant="neutral" size="sm">Platform</Badge>
        ),
    },
    {
      key: 'workflowType',
      header: 'Type',
      width: 'w-[100px]',
      render: (r) => (
        <span className="text-[var(--text-secondary)] uppercase">{r.workflowType}</span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      width: 'w-[120px]',
      render: (r) =>
        r.source === 'platform' ? (
          <span className="text-[var(--text-muted)]">—</span>
        ) : r.currentPublishedVersionId ? (
          <Badge variant="success" size="sm">Published</Badge>
        ) : (
          <Badge variant="neutral" size="sm">Draft</Badge>
        ),
    },
    {
      key: 'lastRun',
      header: 'Last run',
      width: 'min-w-[170px]',
      render: (r) => {
        if (r.source === 'platform' || !r.lastRunAt) {
          return <span className="text-[var(--text-muted)]">—</span>;
        }
        const time = (
          <span className="tabular-nums">{fmtRelative(r.lastRunAt)}</span>
        );
        const chip = r.lastRunStatus ? (
          <RunStatusChip status={r.lastRunStatus} />
        ) : null;
        const inner = (
          <div
            className="flex flex-col gap-1"
            title={fmtDateTime(r.lastRunAt)}
          >
            {time}
            {chip}
          </div>
        );
        return r.lastRunId ? (
          <Link
            to={orchestrationRoutes.campaignRunDetail(r.lastRunId)}
            onClick={(e) => e.stopPropagation()}
            className="block text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            {inner}
          </Link>
        ) : (
          <div className="text-[var(--text-secondary)]">{inner}</div>
        );
      },
    },
    {
      key: 'updatedAt',
      header: 'Updated',
      width: 'w-[180px]',
      render: (r) => (
        <span className="tabular-nums text-[var(--text-secondary)]">
          {fmtDateTime(r.updatedAt)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      width: '170px',
      headerClassName: 'text-right',
      cellClassName: 'text-right',
      render: (r) =>
        r.source === 'platform' ? (
          <div className="flex items-center justify-end gap-1">
            <IconButton
              icon={Copy}
              variant="secondary"
              size="sm"
              label="Clone"
              onClick={(e) => {
                e.stopPropagation();
                setCloneSource(r);
              }}
            />
          </div>
        ) : (
          <div className="flex items-center justify-end gap-1">
            <IconButton
              icon={History}
              variant="ghost"
              size="sm"
              label="Run history"
              onClick={(e) => {
                e.stopPropagation();
                setHistoryTarget(r);
              }}
            />
            <IconButton
              icon={Pencil}
              variant="ghost"
              size="sm"
              label="Edit"
              onClick={(e) => {
                e.stopPropagation();
                navigate(orchestrationRoutes.campaignBuilder(r.id));
              }}
            />
            <IconButton
              icon={Play}
              variant="ghost"
              size="sm"
              label={
                !r.currentPublishedVersionId
                  ? 'Publish the workflow before running it'
                  : runningId === r.id
                    ? 'Starting run…'
                    : 'Run now'
              }
              disabled={!r.currentPublishedVersionId || runningId === r.id}
              onClick={(e) => {
                e.stopPropagation();
                void handleRun(r);
              }}
            />
            <IconButton
              icon={Archive}
              variant="danger"
              size="sm"
              label="Archive"
              onClick={(e) => {
                e.stopPropagation();
                setArchiveTarget(r);
              }}
            />
          </div>
        ),
    },
  ];

  return (
    <>
      <PageSurface
        icon={icon}
        title={title}
        filters={(
          <FilterPills
            options={SOURCE_FILTERS}
            active={activeSource}
            onChange={(id) => setActiveSource(id as SourceFilter)}
          />
        )}
        actions={<Button onClick={() => setShowCreate(true)}>New Workflow</Button>}
      >
        <div className="flex min-h-0 flex-1 flex-col">
          <DataTable<UnifiedRow>
            data={visibleRows}
            columns={columns}
            keyExtractor={(r) => `${r.source}:${r.id}`}
            loading={loading}
            emptyTitle="No workflows yet"
            emptyDescription="Create a custom workflow or clone a platform starter to get going."
            onRowClick={(r) => {
              if (r.source === 'custom') {
                navigate(orchestrationRoutes.campaignBuilder(r.id));
              }
            }}
          />
        </div>
      </PageSurface>
      {showCreate && (
        <CreateWorkflowDialog
          onClose={() => setShowCreate(false)}
          onCreated={(workflow) => {
            setShowCreate(false);
            navigate(orchestrationRoutes.campaignBuilder(workflow.id));
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
            navigate(orchestrationRoutes.campaignBuilder(workflow.id));
          }}
          />
      )}
      <ConfirmDialog
        isOpen={archiveTarget !== null}
        onClose={() => setArchiveTarget(null)}
        onConfirm={() => {
          void handleArchive();
        }}
        title="Archive workflow?"
        description={
          archiveTarget
            ? `"${archiveTarget.name}" will be removed from the active campaigns list. Existing runs are preserved.`
            : ''
        }
        confirmLabel={archivingId === archiveTarget?.id ? 'Archiving…' : 'Archive'}
        variant="danger"
      />
      {historyTarget && (
        <WorkflowRunHistoryOverlay
          workflow={historyTarget}
          onClose={() => setHistoryTarget(null)}
        />
      )}
    </>
  );
}
