import { RefreshCw } from 'lucide-react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Tooltip } from '@/components/ui/Tooltip';
import { decodeApiError, summarizeApiErrorBody } from '@/features/orchestration/contracts/errorDecoder';
import { notificationService } from '@/services/notifications';

import { useActivateDataset, useTriggerCrmSync } from '../queries/crmSourceQueries';

export type DatasetStatus = 'draft' | 'active' | 'active_edited';

function statusBadge(status: DatasetStatus, version: number) {
  if (status === 'active') {
    return { variant: 'success' as const, label: `Active · v${version}` };
  }
  if (status === 'active_edited') {
    return { variant: 'warning' as const, label: 'Active · edited' };
  }
  return { variant: 'neutral' as const, label: 'Draft' };
}

/** Run-controls for the selected dataset: live status, Sync now (Active only), and the
 *  gated Publish/Activate button. Mirrors the dataset-detail publish footer. */
export function DatasetFooter({
  connectionId,
  recordType,
  sourceObject,
  status,
  version,
  canActivate,
  saving,
  lastSyncAt,
}: {
  connectionId: string;
  recordType: string;
  sourceObject: string;
  status: DatasetStatus;
  version: number;
  canActivate: boolean;
  saving: boolean;
  lastSyncAt: string | null;
}) {
  const activate = useActivateDataset(connectionId);
  const sync = useTriggerCrmSync(connectionId);

  const badge = statusBadge(status, version);
  const isActive = status === 'active' || status === 'active_edited';
  const publishLabel = isActive ? `Publish → v${version + 1}` : 'Publish';

  function handleActivate() {
    activate.mutate(recordType, {
      onSuccess: (r) => notificationService.success(`Published v${r.version} · resolved view refreshed`),
      onError: (err) =>
        notificationService.error(summarizeApiErrorBody(decodeApiError(err), 'Publish failed')),
    });
  }

  function handleSync() {
    sync.mutate([sourceObject], {
      onSuccess: () => notificationService.success('Sync queued'),
      onError: (err) =>
        notificationService.error(summarizeApiErrorBody(decodeApiError(err), 'Sync failed')),
    });
  }

  return (
    <div className="flex items-center justify-between gap-3 border-t border-[var(--border-default)] pt-4">
      <div className="flex items-center gap-2 text-[12px] text-[var(--text-secondary)]">
        <Badge variant={badge.variant} size="sm">
          {badge.label}
        </Badge>
        {saving ? <span className="text-[var(--text-muted)]">Saving draft…</span> : null}
        {lastSyncAt ? <span>Last sync {new Date(lastSyncAt).toLocaleString()}</span> : null}
      </div>
      <div className="flex items-center gap-2">
        {isActive ? (
          <Tooltip content="Pull the latest records from this source into the landing store. Read-only on the source.">
            <Button
              variant="secondary"
              icon={RefreshCw}
              isLoading={sync.isPending}
              onClick={handleSync}
            >
              Sync now
            </Button>
          </Tooltip>
        ) : null}
        <Tooltip
          content={
            canActivate
              ? 'Publish this dataset, rebuild the resolved view, and apply the current filter.'
              : 'Map the required fields first to enable publishing.'
          }
        >
          <Button isLoading={activate.isPending} disabled={!canActivate} onClick={handleActivate}>
            {publishLabel}
          </Button>
        </Tooltip>
      </div>
    </div>
  );
}
