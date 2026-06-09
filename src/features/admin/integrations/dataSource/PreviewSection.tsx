import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { decodeApiError, summarizeApiErrorBody } from '@/features/orchestration/contracts/errorDecoder';

import { useDatasetPreview } from '../queries/crmSourceQueries';
import { SampleColumnsTable } from './SampleColumnsTable';

/** Live dry-run of exactly what lands in the database — resolved columns with the current filter applied. */
export function PreviewSection({
  connectionId,
  recordType,
}: {
  connectionId: string;
  recordType: string;
}) {
  const preview = useDatasetPreview(connectionId, recordType);
  const columns = preview.data?.columns ?? [];
  const rows = preview.data?.rows ?? [];

  if (preview.isError) {
    return (
      <Alert variant="warning">
        {summarizeApiErrorBody(decodeApiError(preview.error), 'Could not build a preview for this dataset.')}
      </Alert>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <p className="text-[13px] font-medium text-[var(--text-primary)]">Preview</p>
        <Badge variant="neutral" size="sm">
          filtered · what lands in the database
        </Badge>
      </div>
      <SampleColumnsTable
        columns={columns}
        rows={rows}
        loading={preview.isFetching}
        emptyTitle="No rows match yet"
        emptyDescription="Adjust the mapping or filter, then this preview shows the resolved rows."
      />
    </div>
  );
}
