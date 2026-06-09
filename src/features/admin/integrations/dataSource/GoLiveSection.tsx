import { CheckCircle2, RefreshCw, Rocket } from 'lucide-react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { decodeApiError, summarizeApiErrorBody } from '@/features/orchestration/contracts/errorDecoder';
import { notificationService } from '@/services/notifications';
import type { CrmChainJob } from '@/services/api/crmSource';

import { useActivateDataset, useDatasetJobs, useTriggerCrmSync } from '../queries/crmSourceQueries';
import type { DatasetStatus } from './DatasetFooter';
import { ScheduleSection } from './ScheduleSection';

// The canonical ingestion chain — always shown in full so the operator sees every stage,
// each annotated with the latest run's status (or "pending" before the first sync).
const PIPELINE_STAGES: { jobType: string; label: string }[] = [
  { jobType: 'sync-crm-source', label: 'Sync' },
  { jobType: 'unpack-crm-source', label: 'Unpack' },
  { jobType: 'populate-crm-resolved', label: 'Resolved rebuild' },
  { jobType: 'populate-analytics', label: 'Analytics' },
];

const STATUS_VARIANT: Record<string, 'success' | 'error' | 'info' | 'warning' | 'neutral'> = {
  completed: 'success',
  failed: 'error',
  running: 'info',
  queued: 'neutral',
  retrying: 'warning',
  cancelled: 'warning',
};

/** Step 4 — the only place state-changing controls live: activate the config, run the pipeline,
 *  schedule recurring syncs, and watch the ingestion chain. */
export function GoLiveSection({
  connectionId,
  recordType,
  sourceObject,
  status,
  canActivate,
}: {
  connectionId: string;
  recordType: string;
  sourceObject: string;
  status: DatasetStatus;
  canActivate: boolean;
}) {
  const activate = useActivateDataset(connectionId);
  const sync = useTriggerCrmSync(connectionId);
  const jobsQuery = useDatasetJobs(connectionId, recordType);

  const isActive = status === 'active';
  const needsActivate = status === 'draft' || status === 'active_edited';
  const jobs = jobsQuery.data?.jobs ?? [];
  // jobs arrive newest-first; the first occurrence per type is that stage's latest run.
  const latestByType = new Map<string, CrmChainJob>();
  for (const j of jobs) if (!latestByType.has(j.jobType)) latestByType.set(j.jobType, j);

  function onActivate() {
    activate.mutate(recordType, {
      onSuccess: (r) =>
        notificationService.success(`Activated v${r.version}. The resolved data now reflects this config.`),
      onError: (err) => notificationService.error(summarizeApiErrorBody(decodeApiError(err), 'Activation failed')),
    });
  }

  function onResync() {
    sync.mutate([sourceObject], {
      onSuccess: () => notificationService.success('Sync queued — the chain will refresh this dataset.'),
      onError: (err) => notificationService.error(summarizeApiErrorBody(decodeApiError(err), 'Sync failed')),
    });
  }

  return (
    <div className="flex flex-col gap-6">
      <section className="space-y-3">
        <div>
          <h3 className="text-[13px] font-semibold text-[var(--text-primary)]">Go live</h3>
          <p className="text-[12px] text-[var(--text-secondary)]">
            {needsActivate
              ? 'Publish this configuration to apply the mapping and filter, then run the pipeline.'
              : 'This dataset is live. Resync on demand or set a recurring schedule below.'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {needsActivate ? (
            <Button icon={Rocket} isLoading={activate.isPending} disabled={!canActivate} onClick={onActivate}>
              {status === 'active_edited' ? 'Re-activate' : 'Activate'}
            </Button>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-[12px] font-medium text-[var(--color-success)]">
              <CheckCircle2 className="h-4 w-4" /> Active
            </span>
          )}
          {isActive ? (
            <Button variant="secondary" icon={RefreshCw} isLoading={sync.isPending} onClick={onResync}>
              Sync now
            </Button>
          ) : null}
        </div>
        {needsActivate && !canActivate ? (
          <p className="text-[12px] text-[var(--text-muted)]">Map the required fields before activating.</p>
        ) : null}
      </section>

      <section className="space-y-2">
        <h3 className="text-[13px] font-semibold text-[var(--text-primary)]">Pipeline</h3>
        <p className="text-[12px] text-[var(--text-secondary)]">
          A sync runs the chain: Sync &rarr; Unpack &rarr; Resolved rebuild &rarr; Analytics.
        </p>
        <ul className="space-y-1.5">
          {PIPELINE_STAGES.map((stage) => {
            const job = latestByType.get(stage.jobType);
            return (
              <li
                key={stage.jobType}
                className="flex items-center justify-between gap-3 rounded-[var(--radius-default)] border border-[var(--border-subtle)] px-3 py-2"
              >
                <span className="text-[13px] text-[var(--text-primary)]">{stage.label}</span>
                {job ? (
                  <Badge variant={STATUS_VARIANT[job.status] ?? 'neutral'} size="sm">
                    {job.status}
                  </Badge>
                ) : (
                  <span className="text-[12px] text-[var(--text-muted)]">pending</span>
                )}
              </li>
            );
          })}
        </ul>
      </section>

      <section className="border-t border-[var(--border-default)] pt-4">
        <ScheduleSection connectionId={connectionId} sourceObject={sourceObject} />
      </section>
    </div>
  );
}
