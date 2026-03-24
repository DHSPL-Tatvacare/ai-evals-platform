import type { ReactNode } from 'react';

interface Column<T> {
  key: keyof T;
  header: string;
  render?: (value: T[keyof T], row: T) => ReactNode;
  /** If true, cell text wraps and gets a max-width cap */
  wrap?: boolean;
  /** Optional min-width for the column */
  minWidth?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export default function DataTable<T extends Record<string, any>>({
  columns,
  data,
}: DataTableProps<T>) {
  return (
    <div className="table-wrapper overflow-x-auto rounded-xl my-6" style={{ border: '1px solid var(--border)' }}>
      <table className="w-full text-[13px] leading-relaxed" style={{ borderCollapse: 'collapse', tableLayout: 'auto' }}>
        <thead>
          <tr style={{ background: 'var(--bg-secondary)', borderBottom: '2px solid var(--border)' }}>
            {columns.map((col) => (
              <th
                key={String(col.key)}
                className="text-left px-4 py-3 font-semibold whitespace-nowrap sticky top-0"
                style={{
                  color: 'var(--text)',
                  background: 'var(--bg-secondary)',
                  ...(col.minWidth ? { minWidth: col.minWidth } : {}),
                }}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr
              key={i}
              className="transition-colors"
              style={{ borderBottom: '1px solid var(--border)' }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--surface-hover)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              {columns.map((col) => (
                <td
                  key={String(col.key)}
                  className="px-4 py-3 align-top"
                  style={{
                    color: 'var(--text-secondary)',
                    ...(col.wrap ? { maxWidth: '420px', wordBreak: 'break-word' as const } : { whiteSpace: 'nowrap' as const }),
                  }}
                >
                  {col.render ? col.render(row[col.key], row) : String(row[col.key] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
