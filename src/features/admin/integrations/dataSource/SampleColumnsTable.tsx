import { DataTable, type ColumnDef } from '@/components/ui/DataTable';

interface SampleRow {
  _key: string;
  values: Record<string, string | null>;
}

/** Renders a {columns, rows} sample (unpacked sample / filtered preview) in named columns. */
export function SampleColumnsTable({
  columns,
  rows,
  loading,
  emptyTitle,
  emptyDescription,
}: {
  columns: string[];
  rows: Record<string, string | null>[];
  loading: boolean;
  emptyTitle: string;
  emptyDescription: string;
}) {
  const data: SampleRow[] = rows.map((r, i) => ({
    _key: `${r[columns[0] ?? ''] ?? ''}-${i}`,
    values: r,
  }));

  const cols: ColumnDef<SampleRow>[] = columns.map((c) => ({
    key: c,
    header: c,
    render: (r) => (
      <span className="whitespace-nowrap font-mono text-[12px] text-[var(--text-secondary)]">
        {r.values[c] ?? <span className="text-[var(--text-muted)]">—</span>}
      </span>
    ),
  }));

  return (
    <DataTable<SampleRow>
      data={data}
      columns={cols}
      keyExtractor={(r) => r._key}
      loading={loading}
      minWidth={`${Math.max(640, columns.length * 160)}px`}
      emptyTitle={emptyTitle}
      emptyDescription={emptyDescription}
    />
  );
}
