import { useEffect } from 'react';

import { Alert } from '@/components/ui/Alert';
import { SegmentedControl } from '@/components/ui/SegmentedControl';
import { decodeApiError, summarizeApiErrorBody } from '@/features/orchestration/contracts/errorDecoder';
import type { CrmFieldBinding } from '@/services/api/crmSource';

import { useRawSample, useUnpackedSample } from '../queries/crmSourceQueries';
import { SampleColumnsTable } from './SampleColumnsTable';

type SampleView = 'raw' | 'unpacked';

const SAMPLE_OPTIONS: { value: SampleView; label: string }[] = [
  { value: 'raw', label: 'Raw JSON' },
  { value: 'unpacked', label: 'Unpacked' },
];

/** Read-only guidance sample above the mapping table: the CRM's raw payload, or the
 *  same records run through the current draft bindings. */
export function SampleToggle({
  connectionId,
  recordType,
  bindings,
  view,
  onViewChange,
}: {
  connectionId: string;
  recordType: string;
  bindings: CrmFieldBinding[];
  view: SampleView;
  onViewChange: (next: SampleView) => void;
}) {
  const rawSample = useRawSample(connectionId, recordType);
  const unpacked = useUnpackedSample(connectionId);

  // Re-run the unpacked preview whenever it is shown or the draft bindings change.
  useEffect(() => {
    if (view !== 'unpacked') return;
    unpacked.mutate({ recordType, bindings });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, recordType, bindings]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[13px] font-medium text-[var(--text-primary)]">Sample data</p>
        <SegmentedControl
          options={SAMPLE_OPTIONS}
          value={view}
          onChange={onViewChange}
          aria-label="Sample source"
        />
      </div>
      {view === 'raw' ? (
        <RawSampleBlock sample={rawSample} />
      ) : (
        <UnpackedSampleBlock unpacked={unpacked} />
      )}
    </div>
  );
}

function RawSampleBlock({ sample }: { sample: ReturnType<typeof useRawSample> }) {
  if (sample.isError) {
    return (
      <Alert variant="error">
        {summarizeApiErrorBody(decodeApiError(sample.error), 'Could not load a sample from the CRM.')}
      </Alert>
    );
  }
  const records = sample.data?.records ?? [];
  if (!sample.isLoading && records.length === 0) {
    return <Alert variant="info">No records returned. Sync this connection to pull a sample.</Alert>;
  }
  return (
    <pre className="max-h-80 overflow-auto rounded-[var(--radius-default)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3 font-mono text-[12px] text-[var(--text-secondary)]">
      {sample.isLoading ? 'Loading…' : JSON.stringify(records.map((r) => r.rawPayload), null, 2)}
    </pre>
  );
}

function UnpackedSampleBlock({ unpacked }: { unpacked: ReturnType<typeof useUnpackedSample> }) {
  if (unpacked.isError) {
    return (
      <Alert variant="error">
        {summarizeApiErrorBody(decodeApiError(unpacked.error), 'Could not preview the unpacked sample.')}
      </Alert>
    );
  }
  const columns = unpacked.data?.columns ?? [];
  const rows = unpacked.data?.rows ?? [];
  return (
    <SampleColumnsTable
      columns={columns}
      rows={rows}
      loading={unpacked.isPending}
      emptyTitle="Nothing to unpack yet"
      emptyDescription="Map a few fields, and a sample of the unpacked rows appears here."
    />
  );
}
