import { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, CircleDashed, PlugZap, RefreshCw, Sparkles, X } from 'lucide-react';

import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Combobox, type ComboboxOption } from '@/components/ui/Combobox';
import { ConnectionProviderLogo } from '@/components/ui/ConnectionProviderLogo';
import { DataTable, type ColumnDef } from '@/components/ui/DataTable';
import { Input } from '@/components/ui/Input';
import { RightSlideOverShell } from '@/components/ui/RightSlideOverShell';
import { ApiError } from '@/services/api/client';
import { type Connection } from '@/services/api/orchestrationConnections';
import { notificationService } from '@/services/notifications';
import {
  boundTargets,
  draftToPublishBindings,
  requiredTargets,
  slotTypeOf,
  useCrmMappingDraftStore,
} from '@/stores/crmMappingDraftStore';
import { cn } from '@/utils/cn';

import { useTestConnection } from '../queries';
import {
  useCrmDiscoveredObjects,
  useCrmFieldMap,
  useCrmGrains,
  useCrmSyncActivity,
  usePublishCrmFieldMap,
  useTriggerCrmSync,
  useTriggerCrmUnpack,
} from '../queries/crmSourceQueries';
import { CrmValueMapEditor } from './CrmValueMapEditor';

interface Props {
  connection: Connection;
  onClose: () => void;
}

const SLOT_TYPE_LABELS: Array<[string, string]> = [
  ['text', 'Custom · Text'],
  ['num', 'Custom · Number'],
  ['int', 'Custom · Whole number'],
  ['dt', 'Custom · Date / time'],
  ['bool', 'Custom · Yes / No'],
  ['json', 'Custom · Structured'],
];

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

interface FieldRow {
  field: string;
}

export function CrmMappingEditor({ connection, onClose }: Props) {
  const grainsQuery = useCrmGrains();
  const grainByType = useMemo(
    () => Object.fromEntries((grainsQuery.data?.grains ?? []).map((g) => [g.recordType, g])),
    [grainsQuery.data],
  );

  const [tested, setTested] = useState(false);
  const testMutation = useTestConnection();
  const objectsQuery = useCrmDiscoveredObjects(connection.id, tested);
  const objects = objectsQuery.data?.objects ?? [];

  const [sourceObject, setSourceObject] = useState<string | null>(null);
  const selectedObj = objects.find((o) => o.sourceObject === sourceObject) ?? null;
  const recordType = selectedObj?.recordType ?? null;
  const grain = recordType ? grainByType[recordType] ?? null : null;

  const mappingQuery = useCrmFieldMap(connection.id, recordType);

  const bindings = useCrmMappingDraftStore((s) => s.bindings);
  const startDraft = useCrmMappingDraftStore((s) => s.startDraft);
  const reset = useCrmMappingDraftStore((s) => s.reset);
  const setTargetStandard = useCrmMappingDraftStore((s) => s.setTargetStandard);
  const setTargetSlot = useCrmMappingDraftStore((s) => s.setTargetSlot);
  const setIgnore = useCrmMappingDraftStore((s) => s.setIgnore);
  const setSemanticKey = useCrmMappingDraftStore((s) => s.setSemanticKey);
  const openValueMap = useCrmMappingDraftStore((s) => s.openValueMap);

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

  const publishMutation = usePublishCrmFieldMap(connection.id);
  const syncMutation = useTriggerCrmSync(connection.id);
  const unpackMutation = useTriggerCrmUnpack(connection.id);
  const activityQuery = useCrmSyncActivity(connection.id, true);

  const bound = boundTargets(bindings);
  const required = requiredTargets(grain);
  const missingRequired = required.filter((t) => !bound.has(t));
  const canPublish = Boolean(grain) && missingRequired.length === 0;

  const targetOptions: ComboboxOption[] = useMemo(() => {
    if (!grain) return [];
    return [
      { value: 'ignore', label: "Don't map" },
      ...grain.standardColumns.map((c) => ({ value: `std:${c.target}`, label: c.label, meta: 'Standard' })),
      ...SLOT_TYPE_LABELS.filter(([t]) => (grain.slots[t]?.length ?? 0) > 0).map(([t, label]) => ({
        value: `slot:${t}`,
        label,
        meta: 'Custom field',
      })),
    ];
  }, [grain]);

  function currentTargetValue(field: string): string {
    const b = bindings[field];
    if (!b) return 'ignore';
    if (b.targetKind === 'standard') return `std:${b.target}`;
    if (b.targetKind === 'slot') return `slot:${slotTypeOf(b.target) ?? 'text'}`;
    return 'ignore';
  }

  function onTargetChange(field: string, value: string) {
    if (!grain) return;
    if (value === 'ignore') {
      setIgnore(field);
    } else if (value.startsWith('std:')) {
      const target = value.slice(4);
      const col = grain.standardColumns.find((c) => c.target === target);
      if (col) setTargetStandard(field, col);
    } else if (value.startsWith('slot:')) {
      setTargetSlot(field, value.slice(5));
    }
  }

  function handleTestAndDiscover() {
    testMutation.mutate(connection.id, {
      onSuccess: (result) => {
        if (result.ok) {
          setTested(true);
          notificationService.success(`Connection healthy — ${result.detail}`);
        } else {
          notificationService.error(`Test failed: ${result.detail}`);
        }
      },
      onError: (err) => notificationService.error(errorMessage(err, 'Test failed')),
    });
  }

  function handlePublish() {
    if (!recordType) return;
    publishMutation.mutate(
      { recordType, bindings: draftToPublishBindings(bindings) },
      {
        onSuccess: (r) =>
          notificationService.success(`Mapping published (v${r.version}). Rebuilding from landed data…`),
        onError: (err) => notificationService.error(errorMessage(err, 'Publish failed')),
      },
    );
  }

  const columns: ColumnDef<FieldRow>[] = [
    {
      key: 'field',
      header: 'CRM field',
      render: (r) => <span className="font-mono text-[12px] text-[var(--text-primary)]">{r.field}</span>,
    },
    {
      key: 'target',
      header: 'Maps to',
      width: 'w-[240px]',
      render: (r) => (
        <Combobox
          options={targetOptions}
          value={currentTargetValue(r.field)}
          onChange={(v) => onTargetChange(r.field, v)}
          size="sm"
          placeholder="Don't map"
        />
      ),
    },
    {
      key: 'name',
      header: 'Name',
      width: 'w-[200px]',
      render: (r) => {
        const b = bindings[r.field];
        if (!b) return <span className="text-[var(--text-muted)]">—</span>;
        if (b.targetKind === 'slot') {
          return (
            <Input
              value={b.semanticKey}
              onChange={(e) => setSemanticKey(r.field, e.target.value)}
              placeholder="Field name"
            />
          );
        }
        return <span className="text-[13px] text-[var(--text-secondary)]">{b.semanticKey}</span>;
      },
    },
    {
      key: 'values',
      header: 'Values',
      width: 'w-[110px]',
      render: (r) => {
        const b = bindings[r.field];
        if (!b) return null;
        const count = b.valueMap ? Object.keys(b.valueMap).length : 0;
        return (
          <Button variant="ghost" size="sm" onClick={() => openValueMap(r.field)}>
            {count > 0 ? `Values · ${count}` : 'Values'}
          </Button>
        );
      },
    },
  ];

  const fieldRows: FieldRow[] = (selectedObj?.fields ?? []).map((f) => ({ field: f }));
  const objectOptions: ComboboxOption[] = objects.map((o) => ({
    value: o.sourceObject,
    label: o.sourceObject,
    meta: o.recordType,
  }));

  const discovering = objectsQuery.isFetching;
  const recentRuns = (activityQuery.data?.runs ?? []).slice(0, 5);

  return (
    <RightSlideOverShell
      isOpen
      onClose={onClose}
      widthClassName="w-[var(--overlay-width-lg)] max-w-[95vw]"
    >
      <div className="flex shrink-0 items-start justify-between gap-4 border-b border-[var(--border-default)] bg-[var(--bg-secondary)] px-6 py-4">
        <div className="flex min-w-0 items-center gap-2">
          <ConnectionProviderLogo provider={connection.provider} size={24} />
          <div className="min-w-0">
            <h2 className="truncate text-[16px] font-semibold text-[var(--text-primary)]">
              Field mapping — {connection.name}
            </h2>
            <p className="text-[12px] text-[var(--text-secondary)]">
              Map the CRM&rsquo;s fields to standard columns and custom fields. Nothing here changes
              the connection itself.
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

      <div className="flex-1 space-y-5 overflow-y-auto px-6 py-5">
        {!tested ? (
          <div className="space-y-3">
            <Alert variant="info" title="Test the connection to load its fields">
              We&rsquo;ll make a read-only check, then list the fields the CRM exposes so you can map
              them.
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
            <Button
              variant="secondary"
              icon={RefreshCw}
              onClick={() => {
                setTested(false);
              }}
            >
              Try again
            </Button>
          </div>
        ) : (
          <>
            <div className="max-w-[360px]">
              <label className="mb-1.5 block text-[12px] font-medium text-[var(--text-secondary)]">
                Source object
              </label>
              <Combobox
                options={objectOptions}
                value={sourceObject ?? ''}
                onChange={setSourceObject}
                loading={discovering}
                placeholder={discovering ? 'Discovering…' : 'Select an object to map'}
              />
            </div>

            {grain && selectedObj ? (
              <>
                <CoveragePanel grain={grain} bound={bound} />

                {missingRequired.length > 0 ? (
                  <Alert variant="warning">
                    Bind {missingRequired.map((t) => grainLabel(grain, t)).join(', ')} before publishing
                    — without it rows can&rsquo;t be linked.
                  </Alert>
                ) : null}

                <DataTable<FieldRow>
                  data={fieldRows}
                  columns={columns}
                  keyExtractor={(r) => r.field}
                  loading={mappingQuery.isLoading}
                  minWidth="640px"
                  emptyTitle="No fields"
                  emptyDescription="This object exposes no fields to map."
                />
              </>
            ) : null}
          </>
        )}
      </div>

      <div className="shrink-0 space-y-3 border-t border-[var(--border-default)] bg-[var(--bg-secondary)] px-6 py-4">
        {recentRuns.length > 0 ? (
          <div className="space-y-1">
            <p className="text-[11px] font-medium uppercase tracking-wide text-[var(--text-muted)]">
              Recent activity
            </p>
            {recentRuns.map((run) => (
              <div
                key={run.id}
                className="flex items-center justify-between gap-3 text-[12px] text-[var(--text-secondary)]"
              >
                <span className="flex items-center gap-2">
                  <Badge variant={run.status === 'completed' ? 'success' : 'neutral'} size="sm">
                    {run.syncMode}
                  </Badge>
                  <span>{run.sourceFamily}</span>
                </span>
                <span>
                  {run.recordsUpserted}/{run.recordsScanned} records
                </span>
              </div>
            ))}
          </div>
        ) : null}

        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
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
          </div>
          <Button
            isLoading={publishMutation.isPending}
            disabled={!canPublish}
            onClick={handlePublish}
          >
            Publish mapping
          </Button>
        </div>
      </div>

      <CrmValueMapEditor connectionId={connection.id} recordType={recordType} />
    </RightSlideOverShell>
  );
}

function grainLabel(
  grain: { standardColumns: Array<{ target: string; label: string }> },
  target: string,
): string {
  return grain.standardColumns.find((c) => c.target === target)?.label ?? target;
}

function CoveragePanel({
  grain,
  bound,
}: {
  grain: {
    expectedTargets: string[];
    standardColumns: Array<{ target: string; label: string }>;
    naturalKeyTarget: string;
    leadLinkTarget: string;
    leadLinkRequired: boolean;
  };
  bound: Set<string>;
}) {
  const required = new Set([
    grain.naturalKeyTarget,
    ...(grain.leadLinkRequired ? [grain.leadLinkTarget] : []),
  ]);
  return (
    <div className="flex flex-wrap gap-2">
      {grain.expectedTargets.map((t) => {
        const ok = bound.has(t);
        return (
          <span
            key={t}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px]',
              ok
                ? 'border-[var(--color-success)]/40 text-[var(--text-primary)]'
                : 'border-[var(--border-default)] text-[var(--text-secondary)]',
            )}
          >
            {ok ? (
              <CheckCircle2 className="h-3.5 w-3.5 text-[var(--color-success)]" />
            ) : (
              <CircleDashed className="h-3.5 w-3.5 text-[var(--text-muted)]" />
            )}
            {grainLabel(grain, t)}
            {required.has(t) ? <span className="text-[var(--color-error)]">*</span> : null}
          </span>
        );
      })}
    </div>
  );
}
