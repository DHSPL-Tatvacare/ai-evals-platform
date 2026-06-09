import { Sparkles } from 'lucide-react';

import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { DataTable, type ColumnDef } from '@/components/ui/DataTable';

import { useCrmResolvedPreview } from '../queries/crmSourceQueries';

interface PreviewRow {
  _key: string;
  values: Record<string, string | null>;
}

/** "What the assistant sees" — a sample of the resolved layer in clean, named columns. */
export function ResolvedPreviewPanel({
  connectionId,
  recordType,
}: {
  connectionId: string;
  recordType: string | null;
}) {
  const previewQuery = useCrmResolvedPreview(connectionId, recordType);
  const cols = previewQuery.data?.columns ?? [];
  const rows: PreviewRow[] = (previewQuery.data?.rows ?? []).map((r, i) => ({
    _key: `${r[cols[0] ?? ''] ?? ''}-${i}`,
    values: r,
  }));

  const columns: ColumnDef<PreviewRow>[] = cols.map((c) => ({
    key: c,
    header: c,
    render: (r) => (
      <span className="whitespace-nowrap font-mono text-[12px] text-[var(--text-secondary)]">
        {r.values[c] ?? <span className="text-[var(--text-muted)]">—</span>}
      </span>
    ),
  }));

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-[var(--text-muted)]" />
        <p className="text-[13px] font-medium text-[var(--text-primary)]">Resolved preview</p>
        <Badge variant="neutral" size="sm">
          what the assistant sees
        </Badge>
      </div>
      {cols.length === 0 ? (
        <Alert variant="info">
          Publish a mapping and sync, then a sample of the resolved data appears here — with your
          column names, not the CRM&rsquo;s raw fields.
        </Alert>
      ) : (
        <DataTable<PreviewRow>
          data={rows}
          columns={columns}
          keyExtractor={(r) => r._key}
          loading={previewQuery.isFetching}
          minWidth={`${Math.max(640, cols.length * 160)}px`}
          emptyTitle="No rows yet"
          emptyDescription="Sync and rebuild this connection to populate the resolved layer."
        />
      )}
    </div>
  );
}
