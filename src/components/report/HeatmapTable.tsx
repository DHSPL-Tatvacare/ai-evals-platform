import { cn } from '@/utils/cn';

export interface HeatmapColumn {
  key: string;
  label: string;
  shortLabel?: string;
  max: number;
  greenThreshold: number;
  yellowThreshold: number;
}

export interface HeatmapRow {
  id: string;
  label: string;
  extraColumns?: { label: string; value: string | number; className?: string }[];
}

interface Props {
  rows: HeatmapRow[];
  columns: HeatmapColumn[];
  cells: Record<string, Record<string, number>>;
  selectedRowId?: string | null;
  onRowClick?: (rowId: string) => void;
  className?: string;
}

function cellColor(value: number, green: number, yellow: number): string {
  if (value >= green) return 'bg-[var(--color-success)]/20 text-[var(--color-success)]';
  if (value >= yellow) return 'bg-[var(--color-warning)]/20 text-[var(--color-warning)]';
  return 'bg-[var(--color-error)]/20 text-[var(--color-error)]';
}

export function HeatmapTable({ rows, columns, cells, selectedRowId, onRowClick, className }: Props) {
  return (
    <div className={cn('overflow-x-auto', className)}>
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="border-b-2 border-[var(--border)]">
            <th className="text-left p-2 w-28">Name</th>
            {rows[0]?.extraColumns?.map((ec, i) => (
              <th key={i} className="text-center p-2 w-12">{ec.label}</th>
            ))}
            {columns.map((col) => (
              <th key={col.key} className="text-center p-2" title={col.label}>
                <div className="text-[10px] leading-tight">{col.shortLabel || col.label}</div>
                <div className="text-[10px] text-[var(--text-secondary)]">/{col.max}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              className={cn(
                'border-b border-[var(--border)] cursor-pointer hover:bg-[var(--bg-secondary)] transition-colors',
                selectedRowId === row.id && 'bg-[var(--bg-secondary)] ring-1 ring-[var(--accent)]'
              )}
              onClick={() => onRowClick?.(row.id)}
            >
              <td className="p-2 font-semibold">{row.label}</td>
              {row.extraColumns?.map((ec, i) => (
                <td key={i} className={cn('text-center p-2', ec.className)}>{ec.value}</td>
              ))}
              {columns.map((col) => {
                const val = cells[row.id]?.[col.key] ?? 0;
                return (
                  <td key={col.key} className="text-center p-1.5">
                    <span className={cn('px-2 py-0.5 rounded font-semibold', cellColor(val, col.greenThreshold, col.yellowThreshold))}>
                      {val.toFixed(1)}
                    </span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
