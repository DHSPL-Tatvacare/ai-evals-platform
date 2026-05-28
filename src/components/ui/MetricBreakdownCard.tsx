import { type ReactNode, useMemo, useState } from 'react';
import { BarChart3, type LucideIcon } from 'lucide-react';
import { Card } from './Card';
import { DataTable, type ColumnDef } from './DataTable';
import { PageHeaderSearch } from './PageHeaderSearch';
import { cn } from '@/utils/cn';

export interface MetricBreakdownColumn<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  width?: string;
  /** Right-aligns the numeric column; defaults to true. Set false for the name column. */
  numeric?: boolean;
}

interface MetricBreakdownCardProps<T> {
  title?: string;
  /** Header for the leading name column. */
  nameHeader: ReactNode;
  rows: T[];
  columns: MetricBreakdownColumn<T>[];
  keyExtractor: (row: T) => string;
  renderName: (row: T) => ReactNode;
  headerControl?: ReactNode;
  /** When provided, renders an in-card search filtering on the matcher. */
  searchPlaceholder?: string;
  searchMatch?: (row: T, query: string) => boolean;
  emptyIcon?: LucideIcon;
  emptyTitle?: string;
  emptyDescription?: string;
}

/** Generic uniform breakdown data table. Generalizes the cost SpendBreakdownCard
 *  grammar (name column + right-aligned metric columns + optional search) without
 *  coupling to cost-specific row shapes, so any analytics surface can declare its
 *  own metric columns. */
export function MetricBreakdownCard<T>({
  title,
  nameHeader,
  rows,
  columns,
  keyExtractor,
  renderName,
  headerControl,
  searchPlaceholder,
  searchMatch,
  emptyIcon = BarChart3,
  emptyTitle = 'No data',
  emptyDescription = 'No rows matched the current range or filter.',
}: MetricBreakdownCardProps<T>) {
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || !searchMatch) return rows;
    return rows.filter((row) => searchMatch(row, q));
  }, [rows, query, searchMatch]);

  const tableColumns: ColumnDef<T>[] = [
    {
      key: '__name__',
      header: nameHeader,
      textBehavior: 'truncate',
      render: (row) => renderName(row),
    },
    ...columns.map((col): ColumnDef<T> => ({
      key: col.key,
      header: col.header,
      width: col.width ?? 'w-24',
      cellClassName: cn(
        'tabular-nums text-[var(--text-secondary)]',
        col.numeric !== false && 'text-right',
      ),
      headerClassName: col.numeric !== false ? 'text-right' : undefined,
      render: (row) => col.render(row),
    })),
  ];

  return (
    <Card className="flex h-full min-h-0 flex-col p-4">
      {(title || headerControl || searchPlaceholder) && (
        <div className="mb-3 flex shrink-0 items-center justify-between gap-3">
          {title && <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>}
          <div className="flex items-center gap-2">
            {headerControl}
            {searchPlaceholder && searchMatch && (
              <PageHeaderSearch
                value={query}
                onChange={setQuery}
                placeholder={searchPlaceholder}
                label={searchPlaceholder}
              />
            )}
          </div>
        </div>
      )}
      <div className="flex min-h-0 flex-1 flex-col">
        <DataTable
          columns={tableColumns}
          data={filtered}
          keyExtractor={keyExtractor}
          minWidth="0"
          emptyIcon={emptyIcon}
          emptyTitle={emptyTitle}
          emptyDescription={emptyDescription}
        />
      </div>
    </Card>
  );
}
