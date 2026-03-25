import { useMemo } from 'react';
import { HeatmapTable } from '@/components/report/HeatmapTable';
import type { HeatmapColumn, HeatmapRow } from '@/components/report/HeatmapTable';
import type { AgentSlice, DimensionStats } from '@/types/insideSalesReport';
import { cn } from '@/utils/cn';

interface Props {
  agentSlices: Record<string, AgentSlice>;
  dimensionBreakdown: Record<string, DimensionStats>;
  selectedAgentId: string | null;
  onAgentSelect: (agentId: string | null) => void;
  coachingNote?: string | null;
  className?: string;
}

function scoreColor(score: number): string {
  if (score >= 80) return 'text-[var(--color-success)]';
  if (score >= 65) return 'text-[var(--color-warning)]';
  return 'text-[var(--color-error)]';
}

export function AgentHeatmapTable({
  agentSlices, dimensionBreakdown, selectedAgentId, onAgentSelect, coachingNote, className,
}: Props) {
  const { rows, columns, cells } = useMemo(() => {
    const sorted = Object.entries(agentSlices).sort(([, a], [, b]) => b.avgQaScore - a.avgQaScore);

    const cols: HeatmapColumn[] = Object.entries(dimensionBreakdown).map(([key, dim]) => ({
      key,
      label: dim.label,
      shortLabel: dim.label.length > 10 ? dim.label.slice(0, 8) + '.' : dim.label,
      max: dim.maxPossible,
      greenThreshold: dim.greenThreshold,
      yellowThreshold: dim.yellowThreshold,
    }));

    const hRows: HeatmapRow[] = sorted.map(([id, slice]) => ({
      id,
      label: slice.agentName,
      extraColumns: [
        { label: 'Calls', value: slice.callCount },
        { label: 'Avg', value: slice.avgQaScore.toFixed(1), className: cn(scoreColor(slice.avgQaScore), 'font-bold') },
        {
          label: 'Compl.',
          value: slice.compliance.passed + slice.compliance.failed > 0
            ? `${((slice.compliance.passed / (slice.compliance.passed + slice.compliance.failed)) * 100).toFixed(0)}%`
            : '—',
        },
      ],
    }));

    const hCells: Record<string, Record<string, number>> = {};
    for (const [id, slice] of sorted) {
      hCells[id] = {};
      for (const col of cols) {
        hCells[id][col.key] = slice.dimensions[col.key]?.avg ?? 0;
      }
    }

    return { rows: hRows, columns: cols, cells: hCells };
  }, [agentSlices, dimensionBreakdown]);

  return (
    <div className={cn('space-y-4', className)}>
      {selectedAgentId && (
        <div className="flex items-center gap-2">
          <span className="bg-[var(--accent)] text-white px-3 py-1 rounded-full text-xs">
            Filtered: {agentSlices[selectedAgentId]?.agentName} ({agentSlices[selectedAgentId]?.callCount} calls)
          </span>
          <button
            className="text-xs text-[var(--text-secondary)] underline"
            onClick={() => onAgentSelect(null)}
          >
            Clear filter
          </button>
        </div>
      )}

      <HeatmapTable
        rows={rows}
        columns={columns}
        cells={cells}
        selectedRowId={selectedAgentId}
        onRowClick={(id) => onAgentSelect(selectedAgentId === id ? null : id)}
      />

      {selectedAgentId && coachingNote && (
        <div className="bg-[var(--bg-primary)] p-4 rounded-lg border-l-2 border-[var(--color-warning)] text-sm leading-relaxed text-[var(--text-secondary)]">
          <div className="text-[11px] uppercase text-[var(--color-warning)] mb-2 font-semibold">
            Agent Coaching Notes — {agentSlices[selectedAgentId]?.agentName}
          </div>
          {coachingNote}
        </div>
      )}
    </div>
  );
}
