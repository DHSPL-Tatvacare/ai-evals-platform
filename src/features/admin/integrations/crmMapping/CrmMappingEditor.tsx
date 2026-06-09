import { useEffect, useState } from 'react';
import { PlugZap, RefreshCw, X } from 'lucide-react';

import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Combobox, type ComboboxOption } from '@/components/ui/Combobox';
import { ConnectionProviderLogo } from '@/components/ui/ConnectionProviderLogo';
import { RightSlideOverShell } from '@/components/ui/RightSlideOverShell';
import { SegmentedControl } from '@/components/ui/SegmentedControl';
import { ApiError } from '@/services/api/client';
import { type Connection } from '@/services/api/orchestrationConnections';
import { notificationService } from '@/services/notifications';
import {
  boundTargets,
  requiredTargets,
  useCrmMappingDraftStore,
} from '@/stores/crmMappingDraftStore';

import { useTestConnection } from '../queries';
import {
  useCrmDiscoveredObjects,
  useCrmFieldMap,
  useCrmGrains,
  useCrmSyncActivity,
} from '../queries/crmSourceQueries';
import { CrmValueMapEditor } from './CrmValueMapEditor';
import { EditorActions } from './EditorActions';
import { LineagePipeline } from './LineagePipeline';
import { computeStages } from './mappingStages';
import { MappingFieldsTable } from './MappingFieldsTable';
import { ResolvedPreviewPanel } from './ResolvedPreviewPanel';

interface Props {
  connection: Connection;
  onClose: () => void;
}

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

function grainLabel(grain: { standardColumns: Array<{ target: string; label: string }> }, target: string): string {
  return grain.standardColumns.find((c) => c.target === target)?.label ?? target;
}

export function CrmMappingEditor({ connection, onClose }: Props) {
  const grainsQuery = useCrmGrains();
  const grainByType = Object.fromEntries((grainsQuery.data?.grains ?? []).map((g) => [g.recordType, g]));

  const [tested, setTested] = useState(false);
  const [sourceObject, setSourceObject] = useState<string | null>(null);
  const [view, setView] = useState<'map' | 'preview'>('map');

  const testMutation = useTestConnection();
  const objectsQuery = useCrmDiscoveredObjects(connection.id, tested);
  const objects = objectsQuery.data?.objects ?? [];

  const selectedObj = objects.find((o) => o.sourceObject === sourceObject) ?? null;
  const recordType = selectedObj?.recordType ?? null;
  const grain = recordType ? grainByType[recordType] ?? null : null;

  const mappingQuery = useCrmFieldMap(connection.id, recordType);
  const activityQuery = useCrmSyncActivity(connection.id, true);

  const bindings = useCrmMappingDraftStore((s) => s.bindings);
  const startDraft = useCrmMappingDraftStore((s) => s.startDraft);
  const reset = useCrmMappingDraftStore((s) => s.reset);

  // Hydrate the draft once the object, its grain schema, and any published map are loaded.
  useEffect(() => {
    if (selectedObj && grain && mappingQuery.data) {
      startDraft({
        connectionId: connection.id,
        recordType: selectedObj.recordType,
        sourceObject: selectedObj.sourceObject,
        grain,
        serverBindings: mappingQuery.data.bindings,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedObj?.sourceObject, grain?.recordType, mappingQuery.data]);

  useEffect(() => () => reset(), [reset]);

  const bound = boundTargets(bindings);
  const missingRequired = requiredTargets(grain).filter((t) => !bound.has(t));
  const canPublish = Boolean(grain) && missingRequired.length === 0;

  const latestRun = activityQuery.data?.runs?.[0] ?? null;
  const reprocessing = latestRun?.syncMode === 'unpack' && latestRun.status !== 'completed';
  const publishedVersion = mappingQuery.data?.version ?? 0;

  const stages = computeStages({ hasGrain: Boolean(grain), canPublish, publishedVersion, reprocessing });

  const objectOptions: ComboboxOption[] = objects.map((o) => ({
    value: o.sourceObject,
    label: o.sourceObject,
    meta: o.recordType,
  }));

  function handleTestAndDiscover() {
    testMutation.mutate(connection.id, {
      onSuccess: (result) =>
        result.ok
          ? (setTested(true), notificationService.success(`Connection healthy — ${result.detail}`))
          : notificationService.error(`Test failed: ${result.detail}`),
      onError: (err) => notificationService.error(errorMessage(err, 'Test failed')),
    });
  }

  return (
    <RightSlideOverShell isOpen onClose={onClose} widthClassName="w-[var(--overlay-width-lg)] max-w-[95vw]">
      <div className="flex shrink-0 items-start justify-between gap-4 border-b border-[var(--border-default)] bg-[var(--bg-secondary)] px-6 py-4">
        <div className="flex min-w-0 items-center gap-2">
          <ConnectionProviderLogo provider={connection.provider} size={24} />
          <div className="min-w-0">
            <h2 className="truncate text-[16px] font-semibold text-[var(--text-primary)]">
              Field mapping — {connection.name}
            </h2>
            <p className="text-[12px] text-[var(--text-secondary)]">
              Map the CRM&rsquo;s fields to standard columns and custom fields. Nothing here changes the
              connection itself.
            </p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)]"
          aria-label="Close"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {stages.length > 0 ? (
        <div className="shrink-0 border-b border-[var(--border-default)] px-6 py-3">
          <LineagePipeline stages={stages} />
        </div>
      ) : null}

      <div className="flex flex-1 flex-col overflow-hidden px-6 py-5">
        {!tested ? (
          <div className="space-y-3">
            <Alert variant="info" title="Test the connection to load its fields">
              We&rsquo;ll make a read-only check, then list the fields the CRM exposes so you can map them.
            </Alert>
            <Button icon={PlugZap} isLoading={testMutation.isPending} onClick={handleTestAndDiscover}>
              Test &amp; discover fields
            </Button>
          </div>
        ) : objectsQuery.isError ? (
          <div className="space-y-3">
            <Alert variant="error" title="Couldn&rsquo;t reach the CRM">
              {errorMessage(objectsQuery.error, 'Check the connection credentials and try again.')}
            </Alert>
            <Button variant="secondary" icon={RefreshCw} onClick={() => setTested(false)}>
              Try again
            </Button>
          </div>
        ) : (
          <>
            <div className="mb-4 flex items-end justify-between gap-4">
              <div className="max-w-[360px] flex-1">
                <label className="mb-1.5 block text-[12px] font-medium text-[var(--text-secondary)]">
                  Source object
                </label>
                <Combobox
                  options={objectOptions}
                  value={sourceObject ?? ''}
                  onChange={setSourceObject}
                  loading={objectsQuery.isFetching}
                  placeholder={objectsQuery.isFetching ? 'Discovering…' : 'Select an object to map'}
                />
              </div>
              {grain ? (
                <SegmentedControl
                  value={view}
                  onChange={setView}
                  options={[
                    { value: 'map', label: 'Map fields' },
                    { value: 'preview', label: 'Resolved preview' },
                  ]}
                />
              ) : null}
            </div>

            {!grain || !selectedObj ? (
              <div className="flex flex-1 items-center justify-center text-[13px] text-[var(--text-muted)]">
                Select a source object to begin mapping.
              </div>
            ) : view === 'map' ? (
              <div className="flex min-h-0 flex-1 flex-col gap-3">
                {missingRequired.length > 0 ? (
                  <Alert variant="warning">
                    Bind {missingRequired.map((t) => grainLabel(grain, t)).join(', ')} before publishing —
                    without it rows can&rsquo;t be linked.
                  </Alert>
                ) : null}
                <MappingFieldsTable
                  grain={grain}
                  fields={selectedObj.fields}
                  boundCount={bound.size}
                  loading={mappingQuery.isLoading}
                />
              </div>
            ) : (
              <div className="min-h-0 flex-1 overflow-y-auto">
                <ResolvedPreviewPanel connectionId={connection.id} recordType={recordType} />
              </div>
            )}
          </>
        )}
      </div>

      {tested && !objectsQuery.isError ? (
        <EditorActions
          connectionId={connection.id}
          recordType={recordType}
          canPublish={canPublish}
          publishedVersion={publishedVersion}
          reprocessing={reprocessing}
          latestRun={latestRun}
          onPublished={() => setView('preview')}
        />
      ) : null}

      <CrmValueMapEditor connectionId={connection.id} recordType={recordType} />
    </RightSlideOverShell>
  );
}
