import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Inbox, Trash2 } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';

import { Badge, type BadgeVariant } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { DataTable, type ColumnDef } from '@/components/ui/DataTable';
import { EmptyState } from '@/components/ui/EmptyState';
import { MetricChip } from '@/components/ui/MetricChip';
import { PageSurface } from '@/components/ui/PageSurface';
import { RightSlideOverShell } from '@/components/ui/RightSlideOverShell';
import {
  RowActionsMenu,
  type RowAction,
} from '@/components/ui/RowActionsMenu';
import { Select } from '@/components/ui/Select';
import { usePageMetadata } from '@/config/pageMetadata';
import { useOrchestrationRoutes } from '@/features/orchestration/hooks/useOrchestrationRoutes';
import {
  datasetQueryKeys,
  useDataset,
  useDatasetVersion,
  useDeleteDatasetVersion,
  usePublishDatasetVersion,
} from '@/features/orchestration/queries/datasets';
import {
  decodeApiError,
  summarizeApiErrorBody,
} from '@/features/orchestration/contracts/errorDecoder';
import { ApiError } from '@/services/api/client';
import {
  type DatasetSchemaColumn,
  type DatasetVersionResponse,
} from '@/services/api/orchestrationDatasets';
import { notificationService } from '@/services/notifications';

import { DatasetUploadForm } from './DatasetUploadForm';

// Preview size to request; the server clamps to DATASET_SAMPLE_ROW_LIMIT.
const SAMPLE_ROWS = 100;

function fmtDate(s: string | null): string {
  if (!s) return '—';
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleString();
}

function formatBytes(n: number | null): string {
  if (n == null) return '—';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function describeStrategy(version: DatasetVersionResponse): string {
  if (version.idStrategy === 'uuid') return 'Auto-generated UUIDs';
  return version.idColumn ? `Column: ${version.idColumn}` : 'Column';
}

const STATUS_VARIANT: Record<DatasetVersionResponse['status'], BadgeVariant> = {
  draft: 'neutral',
  published: 'success',
  archived: 'warning',
};

const STATUS_LABEL: Record<DatasetVersionResponse['status'], string> = {
  draft: 'Draft',
  published: 'Published',
  archived: 'Archived',
};

function typeBadgeVariant(t: DatasetSchemaColumn['type']): BadgeVariant {
  switch (t) {
    case 'integer':
    case 'number':
      return 'info';
    case 'boolean':
      return 'warning';
    case 'datetime':
      return 'primary';
    default:
      return 'neutral';
  }
}

function renderCell(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

interface SampleRow {
  recipientId: string;
  payload: Record<string, unknown>;
}

export function DatasetDetail() {
  const { datasetId } = useParams<{ datasetId: string }>();
  const { icon } = usePageMetadata('datasetDetail');
  const orchestrationRoutes = useOrchestrationRoutes();

  const qc = useQueryClient();
  const { data: dataset, isLoading: loading } = useDataset(datasetId);
  const versions = useMemo(() => dataset?.versions ?? [], [dataset]);
  const hasVersions = versions.length > 0;
  const latestVersionId = dataset?.latestVersion?.id ?? null;

  const [uploading, setUploading] = useState(false);
  const [userSelectedVersionId, setUserSelectedVersionId] =
    useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DatasetVersionResponse | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  const selectedVersionId = useMemo(() => {
    if (!hasVersions) return null;
    if (
      userSelectedVersionId &&
      versions.some((v) => v.id === userSelectedVersionId)
    ) {
      return userSelectedVersionId;
    }
    return latestVersionId;
  }, [hasVersions, userSelectedVersionId, versions, latestVersionId]);

  const selectedVersion = useMemo(
    () => versions.find((v) => v.id === selectedVersionId) ?? null,
    [versions, selectedVersionId],
  );

  const { data: versionDetail, isLoading: versionDetailLoading } =
    useDatasetVersion(datasetId, selectedVersionId, SAMPLE_ROWS);

  const deleteVersion = useDeleteDatasetVersion(datasetId ?? '');
  const publishVersion = usePublishDatasetVersion(datasetId ?? '');

  async function handlePublishVersion(version: DatasetVersionResponse) {
    if (!datasetId) return;
    try {
      await publishVersion.mutateAsync(version.id);
      notificationService.success(
        `Published v${version.versionNumber}. Workflows now bind to this version.`,
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        notificationService.error('This version is already published.');
        return;
      }
      notificationService.error(
        summarizeApiErrorBody(decodeApiError(err), 'Failed to publish version.'),
      );
    }
  }

  async function handleDeleteVersion() {
    if (!datasetId || !deleteTarget) return;
    try {
      await deleteVersion.mutateAsync(deleteTarget.id);
      notificationService.success(
        `Deleted version v${deleteTarget.versionNumber}`,
      );
      if (selectedVersionId === deleteTarget.id) {
        setUserSelectedVersionId(null);
      }
      setDeleteTarget(null);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : 'Failed to delete version';
      notificationService.error(msg);
    }
  }

  const versionOptions = useMemo(
    () =>
      versions.map((v) => ({
        value: v.id,
        label: `v${v.versionNumber} · ${v.rowCount.toLocaleString()} rows`,
        description: `${describeStrategy(v)} · ${v.sourceFilename ?? '—'} · ${fmtDate(v.importedAt)}`,
      })),
    [versions],
  );

  const schemaColumns = versionDetail?.schemaDescriptor.columns ?? [];

  const sampleColumns = useMemo<ColumnDef<SampleRow>[]>(() => {
    const cols = versionDetail?.schemaDescriptor.columns ?? [];
    const result: ColumnDef<SampleRow>[] = [
      {
        key: '__recipientId',
        header: 'Recipient ID',
        width: 'w-[150px]',
        textBehavior: 'truncate',
        render: (row) => (
          <span
            title={row.recipientId}
            className="font-mono text-[length:var(--text-table-header)] text-[var(--text-secondary)]"
          >
            {row.recipientId}
          </span>
        ),
      },
    ];
    cols.forEach((c) => {
      result.push({
        key: c.name,
        width: 'w-[180px]',
        textBehavior: 'truncate',
        header: (
          <span className="flex flex-col leading-tight">
            <span className="truncate">{c.name}</span>
            <span className="text-[10px] font-normal normal-case text-[var(--text-muted)]">
              {c.type}
            </span>
          </span>
        ),
        render: (row) => {
          const s = renderCell(row.payload[c.name]);
          return s ? (
            <span title={s} className="text-[var(--text-primary)]">
              {s}
            </span>
          ) : (
            <span className="text-[var(--text-tertiary)]">—</span>
          );
        },
      });
    });
    return result;
  }, [versionDetail]);

  const sampleMinWidth = `${Math.max(980, sampleColumns.length * 175)}px`;
  const sampleRows: SampleRow[] = versionDetail?.sampleRows ?? [];

  const versionActions: RowAction[] = [
    {
      id: 'delete',
      icon: Trash2,
      label: 'Delete this version',
      danger: true,
      onClick: () => {
        if (selectedVersion) setDeleteTarget(selectedVersion);
      },
    },
  ];

  return (
    <>
      <PageSurface
        icon={icon}
        title={dataset?.name ?? (loading ? 'Loading…' : 'Dataset')}
        subtitle={dataset?.description ?? undefined}
        back={{ to: orchestrationRoutes.datasetsTab, label: 'Datasets' }}
        actions={
          <Button onClick={() => setUploading(true)} disabled={!dataset}>
            Upload new version
          </Button>
        }
      >
        <div className="flex min-h-0 flex-1 flex-col gap-5 p-6">
          {!loading && dataset && !hasVersions ? (
            <EmptyState
              fill
              icon={Inbox}
              title="No versions yet"
              description="Upload a CSV or Excel file to create the first version of this dataset."
              action={{
                label: 'Upload file',
                onClick: () => setUploading(true),
              }}
            />
          ) : (
            <>
              <div className="flex items-center gap-2">
                <div className="min-w-[320px] max-w-[460px] flex-1">
                  <Select
                    value={selectedVersionId ?? ''}
                    onChange={(id) => setUserSelectedVersionId(id)}
                    options={versionOptions}
                    placeholder="Select a version"
                    disabled={!hasVersions}
                  />
                </div>
                {selectedVersion ? (
                  <Badge variant={STATUS_VARIANT[selectedVersion.status]} size="sm">
                    {STATUS_LABEL[selectedVersion.status]}
                  </Badge>
                ) : null}
                {selectedVersion && selectedVersion.status === 'draft' ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handlePublishVersion(selectedVersion)}
                    isLoading={
                      publishVersion.isPending &&
                      publishVersion.variables === selectedVersion.id
                    }
                    disabled={publishVersion.isPending}
                  >
                    Publish
                  </Button>
                ) : null}
                {selectedVersion ? (
                  <RowActionsMenu
                    actions={versionActions}
                    open={menuOpen}
                    onOpenChange={setMenuOpen}
                  />
                ) : null}
              </div>

              <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
                <MetricChip
                  label="Rows"
                  value={(
                    versionDetail?.rowCount ??
                    selectedVersion?.rowCount ??
                    0
                  ).toLocaleString()}
                />
                <MetricChip
                  label="Columns"
                  value={versionDetail ? schemaColumns.length : '—'}
                />
                <MetricChip
                  label="ID strategy"
                  value={selectedVersion ? describeStrategy(selectedVersion) : '—'}
                />
                <MetricChip
                  label="Source"
                  value={formatBytes(selectedVersion?.sourceByteSize ?? null)}
                  sub={selectedVersion?.sourceFilename ?? undefined}
                />
                <MetricChip
                  label="Imported"
                  value={fmtDate(selectedVersion?.importedAt ?? null)}
                />
              </div>

              <section className="flex flex-col gap-2">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                  Schema{versionDetail ? ` · ${schemaColumns.length} columns` : ''}
                </h3>
                <div className="max-h-[220px] overflow-auto rounded-[10px] border border-[var(--border-default)]">
                  {schemaColumns.length === 0 ? (
                    <p className="px-3 py-3 text-xs text-[var(--text-muted)]">
                      {versionDetailLoading ? 'Reading schema…' : 'No columns detected.'}
                    </p>
                  ) : (
                    schemaColumns.map((c) => (
                      <div
                        key={c.name}
                        className="flex items-center gap-3 border-b border-[var(--border-subtle)] px-3 py-2 last:border-b-0"
                      >
                        <span
                          className="w-48 shrink-0 truncate text-[13px] font-medium text-[var(--text-primary)]"
                          title={c.name}
                        >
                          {c.name}
                        </span>
                        <Badge variant={typeBadgeVariant(c.type)} size="sm">
                          {c.type}
                        </Badge>
                        <span className="w-28 shrink-0 text-right tabular-nums text-[11px] text-[var(--text-muted)]">
                          {(c.distinctCount ?? 0).toLocaleString()} distinct
                        </span>
                        <span
                          className="flex-1 truncate text-[11px] text-[var(--text-secondary)]"
                          title={(c.sampleValues ?? []).join(', ')}
                        >
                          {(c.sampleValues ?? []).join(', ') || '—'}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </section>

              {hasVersions && selectedVersionId ? (
                <section className="flex min-h-0 flex-1 flex-col gap-2">
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                    Sample rows
                    {versionDetail
                      ? ` · showing ${sampleRows.length.toLocaleString()} of ${versionDetail.rowCount.toLocaleString()}`
                      : ''}
                  </h3>
                  <DataTable<SampleRow>
                    data={sampleRows}
                    columns={sampleColumns}
                    keyExtractor={(r) => r.recipientId}
                    loading={versionDetailLoading}
                    minWidth={sampleMinWidth}
                    emptyTitle="No sample rows"
                    emptyDescription="The selected version has no rows to preview."
                  />
                </section>
              ) : null}
            </>
          )}
        </div>
      </PageSurface>

      <RightSlideOverShell isOpen={uploading} onClose={() => setUploading(false)}>
        {uploading && datasetId ? (
          <DatasetUploadForm
            datasetId={datasetId}
            onClose={() => setUploading(false)}
            onUploaded={(version) => {
              setUploading(false);
              setUserSelectedVersionId(version.id);
              if (datasetId) {
                qc.invalidateQueries({
                  queryKey: datasetQueryKeys.detail(datasetId),
                });
                qc.invalidateQueries({
                  queryKey: ['orchestration', 'datasets', 'list'],
                });
              }
            }}
          />
        ) : null}
      </RightSlideOverShell>

      <ConfirmDialog
        isOpen={Boolean(deleteTarget)}
        onClose={() =>
          deleteVersion.isPending ? null : setDeleteTarget(null)
        }
        onConfirm={handleDeleteVersion}
        title="Delete version"
        description={
          deleteTarget
            ? `Delete v${deleteTarget.versionNumber}? Workflows bound to this exact version will fail until rebound.`
            : ''
        }
        confirmLabel={deleteVersion.isPending ? 'Deleting…' : 'Delete'}
        variant="danger"
        isLoading={deleteVersion.isPending}
      />
    </>
  );
}
