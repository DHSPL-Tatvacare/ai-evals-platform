import { useState } from 'react';
import { BarChart3 } from 'lucide-react';
import { cn } from '@/utils';
import { EmptyState } from '@/components/ui';

interface ColumnHeader {
  id: string;
  label: string;
  sublabel?: string;
}

interface HeatmapRow {
  id: string;
  label: string;
  sublabel?: string;
  cells: (number | null)[];
  average: number;
}

interface HeatmapProps {
  columnHeaders: ColumnHeader[];
  rows: HeatmapRow[];
  formatValue?: (value: number) => string;
  rowHeaderLabel?: string;
  onColumnClick?: (id: string) => void;
  emptyMessage?: string;
}

/**
 * Map a 0–1 rate to a heatmap tier using design system CSS variables.
 * Returns { bg, text } CSS variable references — theme-aware in light + dark.
 */
function heatmapTier(rate: number | null): { bg: string; text: string } {
  if (rate === null) return { bg: 'var(--heatmap-null-bg)', text: 'var(--heatmap-null-text)' };
  if (rate >= 0.85) return { bg: 'var(--heatmap-great-bg)', text: 'var(--heatmap-great-text)' };
  if (rate >= 0.70) return { bg: 'var(--heatmap-good-bg)', text: 'var(--heatmap-good-text)' };
  if (rate >= 0.50) return { bg: 'var(--heatmap-mid-bg)', text: 'var(--heatmap-mid-text)' };
  if (rate >= 0.30) return { bg: 'var(--heatmap-low-bg)', text: 'var(--heatmap-low-text)' };
  return { bg: 'var(--heatmap-critical-bg)', text: 'var(--heatmap-critical-text)' };
}

function defaultFormat(value: number): string {
  return `${(value * 100).toFixed(0)}%`;
}

export default function Heatmap({
  columnHeaders,
  rows,
  formatValue = defaultFormat,
  rowHeaderLabel = 'Rule',
  onColumnClick,
  emptyMessage = 'No data available.',
}: HeatmapProps) {
  const [hoveredCell, setHoveredCell] = useState<{ row: number; col: number } | null>(null);

  if (rows.length === 0) {
    return <EmptyState icon={BarChart3} title="No data" description={emptyMessage} compact />;
  }

  const colCount = columnHeaders.length;
  const rotateHeaders = colCount > 8;

  return (
    <div className="overflow-x-auto rounded border border-[var(--border-subtle)]">
      <div
        className="min-w-fit"
        style={{
          display: 'grid',
          gridTemplateColumns: `200px repeat(${colCount}, minmax(44px, 1fr)) 64px`,
        }}
      >
        {/* Header row */}
        <div className="bg-[var(--bg-secondary)] border-b border-[var(--border-subtle)] px-3 py-2 text-[10px] uppercase tracking-wider font-semibold text-[var(--text-muted)] sticky left-0 z-10">
          {rowHeaderLabel}
        </div>
        {columnHeaders.map((col) => (
          <div
            key={col.id}
            className={cn(
              'bg-[var(--bg-secondary)] border-b border-[var(--border-subtle)] px-1 py-2 text-center',
              onColumnClick && 'cursor-pointer hover:bg-[var(--bg-tertiary)]',
            )}
            onClick={() => onColumnClick?.(col.id)}
            title={`${col.label}${col.sublabel ? ` · ${col.sublabel}` : ''}`}
          >
            <div
              className={cn(
                'text-[10px] font-medium text-[var(--text-secondary)] truncate',
                rotateHeaders && 'writing-mode-vertical',
              )}
              style={rotateHeaders ? { writingMode: 'vertical-lr', transform: 'rotate(180deg)', maxHeight: '80px' } : undefined}
            >
              {col.label}
            </div>
            {col.sublabel && !rotateHeaders && (
              <div className="text-[9px] text-[var(--text-muted)] truncate">{col.sublabel}</div>
            )}
          </div>
        ))}
        <div className="bg-[var(--bg-secondary)] border-b border-[var(--border-subtle)] px-1 py-2 text-center text-[10px] uppercase tracking-wider font-semibold text-[var(--text-muted)]">
          Avg
        </div>

        {/* Data rows */}
        {rows.map((row, rowIdx) => (
          <RowContent
            key={row.id}
            row={row}
            rowIdx={rowIdx}
            formatValue={formatValue}
            hoveredCell={hoveredCell}
            setHoveredCell={setHoveredCell}
          />
        ))}
      </div>
    </div>
  );
}

function RowContent({
  row,
  rowIdx,
  formatValue,
  hoveredCell,
  setHoveredCell,
}: {
  row: HeatmapRow;
  rowIdx: number;
  formatValue: (v: number) => string;
  hoveredCell: { row: number; col: number } | null;
  setHoveredCell: (v: { row: number; col: number } | null) => void;
}) {
  const bgAlt = rowIdx % 2 === 0 ? 'bg-[var(--bg-primary)]' : 'bg-[var(--bg-secondary)]';

  return (
    <>
      {/* Row header — sticky left */}
      <div
        className={cn(
          bgAlt,
          'border-b border-[var(--border-subtle)] px-3 py-1.5 sticky left-0 z-10',
        )}
        title={`${row.label}${row.sublabel ? ` (${row.sublabel})` : ''}`}
      >
        <div className="text-[11px] font-medium text-[var(--text-primary)] truncate">{row.label}</div>
        {row.sublabel && (
          <div className="text-[9px] text-[var(--text-muted)] truncate">{row.sublabel}</div>
        )}
      </div>

      {/* Data cells */}
      {row.cells.map((value, colIdx) => {
        const isHovered = hoveredCell?.row === rowIdx && hoveredCell?.col === colIdx;
        const tier = heatmapTier(value);

        return (
          <div
            key={colIdx}
            className={cn(
              'border-b border-[var(--border-subtle)] flex items-center justify-center relative transition-all',
              isHovered && 'ring-2 ring-[var(--color-brand-accent)] z-20',
            )}
            style={{ backgroundColor: tier.bg }}
            onMouseEnter={() => setHoveredCell({ row: rowIdx, col: colIdx })}
            onMouseLeave={() => setHoveredCell(null)}
          >
            <span
              className="text-[10px] font-semibold"
              style={{ color: tier.text }}
            >
              {value !== null ? formatValue(value) : '\u2014'}
            </span>

            {/* Tooltip on hover */}
            {isHovered && value !== null && (
              <div className="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 bg-[var(--bg-elevated)] border border-[var(--border-default)] rounded px-2 py-1 text-[10px] text-[var(--text-primary)] shadow-lg whitespace-nowrap z-30">
                {formatValue(value)}
              </div>
            )}
          </div>
        );
      })}

      {/* Avg column */}
      <div
        className={cn(
          bgAlt,
          'border-b border-[var(--border-subtle)] flex items-center justify-center',
        )}
      >
        <span
          className="text-[11px] font-bold"
          style={{ color: heatmapTier(row.average).text }}
        >
          {formatValue(row.average)}
        </span>
      </div>
    </>
  );
}
