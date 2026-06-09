import { RefreshCw, Sparkles } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { Tooltip } from '@/components/ui/Tooltip';
import { ApiError } from '@/services/api/client';
import { type CrmSyncRun } from '@/services/api/crmSource';
import { notificationService } from '@/services/notifications';
import { draftToPublishBindings, useCrmMappingDraftStore } from '@/stores/crmMappingDraftStore';
import { cn } from '@/utils/cn';

import {
  usePublishCrmFieldMap,
  useTriggerCrmSync,
  useTriggerCrmUnpack,
} from '../queries/crmSourceQueries';

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

function LifecycleStatus({
  publishing,
  reprocessing,
  publishedVersion,
  latestRun,
  boundCount,
}: {
  publishing: boolean;
  reprocessing: boolean;
  publishedVersion: number;
  latestRun: CrmSyncRun | null;
  boundCount: number;
}) {
  const active = publishing || reprocessing;
  const color = active
    ? 'var(--text-brand)'
    : publishedVersion > 0
      ? 'var(--color-success)'
      : 'var(--text-muted)';

  let text: string;
  if (publishing) text = 'Publishing mapping…';
  else if (reprocessing) text = 'Re-processing landed data…';
  else if (publishedVersion > 0) {
    text = `Published v${publishedVersion}`;
    if (latestRun) text += ` · last run ${latestRun.recordsUpserted}/${latestRun.recordsScanned} records`;
  } else text = `${boundCount} field${boundCount === 1 ? '' : 's'} mapped — not yet published`;

  return (
    <div className="flex items-center gap-2 text-[12px] text-[var(--text-secondary)]">
      <span className={cn('h-2 w-2 rounded-full', active && 'animate-pulse')} style={{ backgroundColor: color }} aria-hidden />
      <span>{text}</span>
    </div>
  );
}

export function EditorActions({
  connectionId,
  recordType,
  canPublish,
  publishedVersion,
  reprocessing,
  latestRun,
  onPublished,
}: {
  connectionId: string;
  recordType: string | null;
  canPublish: boolean;
  publishedVersion: number;
  reprocessing: boolean;
  latestRun: CrmSyncRun | null;
  onPublished: () => void;
}) {
  const bindings = useCrmMappingDraftStore((s) => s.bindings);
  const boundCount = Object.keys(bindings).length;

  const publishMutation = usePublishCrmFieldMap(connectionId);
  const syncMutation = useTriggerCrmSync(connectionId);
  const unpackMutation = useTriggerCrmUnpack(connectionId);

  function handlePublish() {
    if (!recordType) return;
    publishMutation.mutate(
      { recordType, bindings: draftToPublishBindings(bindings) },
      {
        onSuccess: (r) => {
          notificationService.success(`Mapping published (v${r.version}). Re-processing landed data…`);
          onPublished();
        },
        onError: (err) => notificationService.error(errorMessage(err, 'Publish failed')),
      },
    );
  }

  return (
    <div className="shrink-0 space-y-3 border-t border-[var(--border-default)] bg-[var(--bg-secondary)] px-6 py-4">
      <LifecycleStatus
        publishing={publishMutation.isPending}
        reprocessing={reprocessing}
        publishedVersion={publishedVersion}
        latestRun={latestRun}
        boundCount={boundCount}
      />
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Tooltip content="Pull the latest leads and calls from the CRM into the landing store. Read-only on the CRM.">
            <Button
              variant="secondary"
              icon={RefreshCw}
              isLoading={syncMutation.isPending}
              onClick={() =>
                syncMutation.mutate(undefined, {
                  onSuccess: () => notificationService.success('Sync queued'),
                  onError: (err) => notificationService.error(errorMessage(err, 'Sync failed')),
                })
              }
            >
              Sync now
            </Button>
          </Tooltip>
          <Tooltip content="Re-apply your current mapping to data already pulled — no CRM call.">
            <Button
              variant="ghost"
              icon={Sparkles}
              isLoading={unpackMutation.isPending}
              onClick={() =>
                unpackMutation.mutate(undefined, {
                  onSuccess: () => notificationService.success('Rebuild queued'),
                  onError: (err) => notificationService.error(errorMessage(err, 'Rebuild failed')),
                })
              }
            >
              Rebuild
            </Button>
          </Tooltip>
        </div>
        <Tooltip
          content={
            canPublish
              ? 'Save this mapping, rebuild the resolved view Sherlock reads, and re-process landed data.'
              : 'Bind the required fields first to enable publishing.'
          }
        >
          <Button isLoading={publishMutation.isPending} disabled={!canPublish} onClick={handlePublish}>
            Publish mapping
          </Button>
        </Tooltip>
      </div>
    </div>
  );
}
