import { ArrowRight } from 'lucide-react';

import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { decodeApiError, summarizeApiErrorBody } from '@/features/orchestration/contracts/errorDecoder';
import { useCrmMappingDraftStore } from '@/stores/crmMappingDraftStore';

import { useDatasetPreview } from '../queries/crmSourceQueries';
import { SampleColumnsTable } from './SampleColumnsTable';

// Logical destinations per grain — the TXN table a dataset writes and the analytics surface it feeds.
const LANDING: Record<string, { txn: string; resolved: string; analytics: string }> = {
  lead: { txn: 'crm_lead', resolved: 'dim_lead (resolved)', analytics: 'dim_lead · Sherlock' },
  activity: {
    txn: 'crm_activity',
    resolved: 'fact_lead_activity (resolved)',
    analytics: 'fact_lead_activity · Sherlock',
  },
};

function recordLabel(recordType: string): string {
  return recordType.charAt(0).toUpperCase() + recordType.slice(1);
}

function LineageNode({ label, sub }: { label: string; sub: string }) {
  return (
    <div className="rounded-[var(--radius-default)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
      <p className="font-mono text-[12px] text-[var(--text-primary)]">{label}</p>
      <p className="text-[11px] text-[var(--text-muted)]">{sub}</p>
    </div>
  );
}

/** Where this dataset's rows land: source → TXN table → resolved view → analytics surface. */
function LandingLineage({
  recordType,
  standardCount,
  customCount,
}: {
  recordType: string;
  standardCount: number;
  customCount: number;
}) {
  const dest = LANDING[recordType] ?? LANDING.lead;
  return (
    <div className="space-y-2 rounded-[var(--radius-default)] border border-[var(--border-subtle)] p-3">
      <p className="text-[12px] font-medium text-[var(--text-secondary)]">Where this lands</p>
      <div className="flex flex-wrap items-center gap-2">
        <LineageNode label={`CRM ${recordLabel(recordType)}`} sub="source" />
        <ArrowRight className="h-3.5 w-3.5 text-[var(--text-muted)]" aria-hidden />
        <LineageNode label={dest.txn} sub={`${standardCount} standard · ${customCount} custom fields`} />
        <ArrowRight className="h-3.5 w-3.5 text-[var(--text-muted)]" aria-hidden />
        <LineageNode label={dest.resolved} sub="filtered view" />
        <ArrowRight className="h-3.5 w-3.5 text-[var(--text-muted)]" aria-hidden />
        <LineageNode label={dest.analytics} sub="analytics & reporting" />
      </div>
    </div>
  );
}

/** Live dry-run of exactly what lands, plus the lineage of where it goes. */
export function PreviewSection({
  connectionId,
  recordType,
}: {
  connectionId: string;
  recordType: string;
}) {
  const preview = useDatasetPreview(connectionId, recordType);
  const bindings = useCrmMappingDraftStore((s) => s.bindings);

  const columns = preview.data?.columns ?? [];
  const rows = preview.data?.rows ?? [];
  const active = Object.values(bindings).filter((b) => b.targetKind !== 'ignore');
  const standardCount = active.filter((b) => b.targetKind === 'standard').length;
  const customCount = active.filter((b) => b.targetKind === 'slot').length;

  return (
    <div className="flex flex-col gap-4">
      <LandingLineage recordType={recordType} standardCount={standardCount} customCount={customCount} />

      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <p className="text-[13px] font-medium text-[var(--text-primary)]">Preview</p>
          <Badge variant="neutral" size="sm">
            filtered · what lands in the database
          </Badge>
        </div>
        {preview.isError ? (
          <Alert variant="warning">
            {summarizeApiErrorBody(decodeApiError(preview.error), 'Could not build a preview for this dataset.')}
          </Alert>
        ) : (
          <SampleColumnsTable
            columns={columns}
            rows={rows}
            loading={preview.isFetching}
            emptyTitle="No rows match yet"
            emptyDescription="Adjust the mapping or filter, then this preview shows the resolved rows."
          />
        )}
      </div>
    </div>
  );
}
