import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Database } from 'lucide-react';

import { Badge } from '@/components/ui/Badge';
import { Skeleton } from '@/components/ui/Skeleton';
import { ConnectionProviderLogo } from '@/components/ui/ConnectionProviderLogo';
import { PageSurface } from '@/components/ui/PageSurface';
import { routes } from '@/config/routes';
import { notificationService } from '@/services/notifications';
import { decodeApiError, summarizeApiErrorBody } from '@/features/orchestration/contracts/errorDecoder';
import { cn } from '@/utils/cn';

import { useConnection } from '../queries';
import { useConnectionDatasets } from '../queries/crmSourceQueries';
import type { CrmDatasetSummary } from '@/services/api/crmSource';
import { DatasetSections } from './DatasetSections';
import type { DatasetStatus } from './DatasetFooter';

function statusVariant(status: string): 'success' | 'neutral' {
  return status === 'active' ? 'success' : 'neutral';
}

function statusLabel(status: string): string {
  return status === 'active' ? 'Active' : 'Draft';
}

function datasetLabel(recordType: string): string {
  return recordType.charAt(0).toUpperCase() + recordType.slice(1);
}

function StatusPill({ status, version }: { status: DatasetStatus; version: number }) {
  if (status === 'active') {
    return (
      <Badge variant="success" size="sm">
        Active · v{version}
      </Badge>
    );
  }
  if (status === 'active_edited') {
    return (
      <Badge variant="warning" size="sm">
        Active · edited
      </Badge>
    );
  }
  return (
    <Badge variant="neutral" size="sm">
      Draft
    </Badge>
  );
}

interface DatasetRailProps {
  datasets: CrmDatasetSummary[];
  selected: string | null;
  loading: boolean;
  onSelect: (recordType: string) => void;
}

function DatasetRail({ datasets, selected, loading, onSelect }: DatasetRailProps) {
  return (
    <div className="flex w-60 flex-shrink-0 flex-col gap-1 border-r border-[var(--border-subtle)] p-3">
      <div className="px-2 pb-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        Datasets
      </div>
      {loading ? (
        <div className="space-y-1.5 px-1 pt-1">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
        </div>
      ) : datasets.length === 0 ? (
        <div className="px-2 py-1 text-[12px] text-[var(--text-secondary)]">
          This connection exposes no datasets.
        </div>
      ) : (
        datasets.map((d) => (
          <button
            key={d.recordType}
            type="button"
            onClick={() => onSelect(d.recordType)}
            className={cn(
              'flex items-center justify-between gap-2 rounded-md px-2 py-2 text-left text-[13px] transition-colors',
              selected === d.recordType
                ? 'bg-[var(--bg-tertiary)] text-[var(--text-primary)]'
                : 'text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)]',
            )}
          >
            <span className="truncate font-medium">{datasetLabel(d.recordType)}</span>
            <Badge variant={statusVariant(d.status)} size="sm">
              {statusLabel(d.status)}
            </Badge>
          </button>
        ))
      )}
    </div>
  );
}

export function ConnectionDataPage() {
  const { connectionId = '' } = useParams<{ connectionId: string }>();
  const connectionQuery = useConnection(connectionId);
  const datasetsQuery = useConnectionDatasets(connectionId);
  const [picked, setPicked] = useState<string | null>(null);
  const [status, setStatus] = useState<DatasetStatus | null>(null);

  const datasets = datasetsQuery.data?.datasets ?? [];
  // Effective selection: explicit user pick, else default to the first dataset.
  const selected = picked ?? datasets[0]?.recordType ?? null;
  const selectedDataset = datasets.find((d) => d.recordType === selected) ?? null;

  useEffect(() => {
    if (datasetsQuery.error) {
      notificationService.error(
        summarizeApiErrorBody(decodeApiError(datasetsQuery.error), 'Failed to load datasets'),
      );
    }
  }, [datasetsQuery.error]);

  const connection = connectionQuery.data;
  const title = connection ? connection.name : 'Connection data';

  return (
    <PageSurface
      icon={Database}
      title={title}
      back={{ to: routes.adminIntegrations, label: 'Integrations' }}
      subtitle={
        connection ? (
          <span className="flex items-center gap-2">
            <ConnectionProviderLogo provider={connection.provider} size={16} />
            <span className="text-[12px] text-[var(--text-secondary)]">
              {selectedDataset ? datasetLabel(selectedDataset.recordType) : 'Manage mapping, filter, and schedule'}
            </span>
          </span>
        ) : undefined
      }
      actions={
        status && selectedDataset ? <StatusPill status={status} version={selectedDataset.version} /> : undefined
      }
      bleed
    >
      <div className="flex min-h-0 flex-1">
        <DatasetRail
          datasets={datasets}
          selected={selected}
          loading={datasetsQuery.isLoading}
          onSelect={setPicked}
        />
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          {selectedDataset ? (
            <DatasetSections
              key={selectedDataset.recordType}
              connectionId={connectionId}
              appId={connection?.appId ?? ''}
              dataset={selectedDataset}
              onStatusChange={setStatus}
            />
          ) : (
            <div className="p-6 text-[13px] text-[var(--text-secondary)]">
              Select a dataset to manage its mapping and filter.
            </div>
          )}
        </div>
      </div>
    </PageSurface>
  );
}
