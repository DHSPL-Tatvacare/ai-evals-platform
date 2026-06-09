import { useState } from 'react';
import { X } from 'lucide-react';

import { Alert } from '@/components/ui/Alert';
import { RightSlideOverShell } from '@/components/ui/RightSlideOverShell';
import { SegmentedControl } from '@/components/ui/SegmentedControl';
import { decodeApiError, summarizeApiErrorBody } from '@/features/orchestration/contracts/errorDecoder';

import { useRawSample } from '../queries/crmSourceQueries';
import { SampleColumnsTable } from './SampleColumnsTable';

type SampleView = 'raw' | 'tabular';

const SAMPLE_OPTIONS: { value: SampleView; label: string }[] = [
  { value: 'raw', label: 'Raw JSON' },
  { value: 'tabular', label: 'Tabular' },
];

/** Reference overlay over the connection's raw sample payload — Raw JSON or a flattened
 *  tabular view. Read-only guidance while mapping; never a competing step. */
export function SampleDataOverlay({
  connectionId,
  recordType,
  onClose,
}: {
  connectionId: string;
  recordType: string;
  onClose: () => void;
}) {
  const [view, setView] = useState<SampleView>('raw');
  const sample = useRawSample(connectionId, recordType);
  const records = sample.data?.records ?? [];

  return (
    <RightSlideOverShell isOpen onClose={onClose} zIndexClassName="z-[var(--z-popover)]">
      <div className="flex shrink-0 items-start justify-between gap-4 border-b border-[var(--border-default)] bg-[var(--bg-secondary)] px-6 py-4">
        <div className="min-w-0">
          <h3 className="text-[15px] font-semibold text-[var(--text-primary)]">Sample data</h3>
          <p className="truncate text-[12px] text-[var(--text-secondary)]">
            A live sample from the CRM for reference while you map.
          </p>
        </div>
        <button
          onClick={onClose}
          className="text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)]"
          aria-label="Close"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
        <SegmentedControl
          options={SAMPLE_OPTIONS}
          value={view}
          onChange={setView}
          aria-label="Sample view"
        />

        {sample.isError ? (
          <Alert variant="error">
            {summarizeApiErrorBody(decodeApiError(sample.error), 'Could not load a sample from the CRM.')}
          </Alert>
        ) : !sample.isLoading && records.length === 0 ? (
          <Alert variant="info">No records returned. Sync this connection to pull a sample.</Alert>
        ) : view === 'raw' ? (
          <pre className="overflow-auto rounded-[var(--radius-default)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3 font-mono text-[12px] text-[var(--text-secondary)]">
            {sample.isLoading ? 'Loading…' : JSON.stringify(records.map((r) => r.rawPayload), null, 2)}
          </pre>
        ) : (
          <SampleColumnsTable
            columns={tabularColumns(records)}
            rows={tabularRows(records)}
            loading={sample.isLoading}
            emptyTitle="Nothing to show"
            emptyDescription="Sync this connection to pull a sample."
          />
        )}
      </div>
    </RightSlideOverShell>
  );
}

function tabularColumns(records: { rawPayload: Record<string, unknown> }[]): string[] {
  const keys = new Set<string>();
  for (const r of records) {
    for (const k of Object.keys(r.rawPayload)) keys.add(k);
  }
  return [...keys];
}

function tabularRows(records: { rawPayload: Record<string, unknown> }[]): Record<string, string | null>[] {
  const columns = tabularColumns(records);
  return records.map((r) => {
    const row: Record<string, string | null> = {};
    for (const c of columns) {
      const v = r.rawPayload[c];
      row[c] = v == null ? null : typeof v === 'object' ? JSON.stringify(v) : String(v);
    }
    return row;
  });
}
