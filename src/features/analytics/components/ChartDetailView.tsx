import { useEffect, useState, useCallback } from 'react';
import { ArrowLeft, RefreshCw, Trash2, Eye, EyeOff } from 'lucide-react';
import { analyticsLibraryApi } from '@/services/api/analyticsLibraryApi';
import { notificationService } from '@/services/notifications';
import { Button, Badge, VisibilityBadge } from '@/components/ui';
import { IconButton } from '@/components/ui/IconButton';
import { ChartRenderer } from './ChartRenderer';
import type { SavedChart } from '../types';

interface ChartDetailViewProps {
  chart: SavedChart;
  onBack: () => void;
  onDelete?: (id: string) => void;
  onUpdate?: (updated: SavedChart) => void;
}

export function ChartDetailView({ chart, onBack, onDelete, onUpdate }: ChartDetailViewProps) {
  const [data, setData] = useState<Record<string, unknown>[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [visibility, setVisibility] = useState(chart.visibility);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await analyticsLibraryApi.getChartData(chart.id);
      setData(result.data);
    } catch {
      notificationService.error('Failed to load chart data');
    } finally {
      setLoading(false);
    }
  }, [chart.id]);

  useEffect(() => { load(); }, [load]);

  const handleToggleVisibility = async () => {
    setToggling(true);
    const newVis = visibility === 'shared' ? 'private' : 'shared';
    try {
      const updated = await analyticsLibraryApi.updateChart(chart.id, { visibility: newVis });
      setVisibility(updated.visibility);
      onUpdate?.(updated);
      notificationService.success(newVis === 'shared' ? 'Chart shared' : 'Chart set to private');
    } catch {
      notificationService.error('Failed to update visibility');
    } finally {
      setToggling(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await analyticsLibraryApi.deleteChart(chart.id);
      notificationService.success('Chart deleted');
      onDelete?.(chart.id);
      onBack();
    } catch {
      notificationService.error('Failed to delete chart');
      setDeleting(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border-default)]">
        <div className="flex items-center gap-3 min-w-0">
          <IconButton icon={ArrowLeft} label="Back" variant="ghost" size="sm" onClick={onBack} />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold text-[var(--text-primary)] truncate">{chart.title}</h2>
              <Badge variant="info" size="sm">{chart.chartConfig.type.replace(/_/g, ' ')}</Badge>
              <VisibilityBadge visibility={visibility} compact />
            </div>
            {chart.sourceQuestion && (
              <p className="text-xs text-[var(--text-muted)] mt-0.5 truncate max-w-[600px]">{chart.sourceQuestion}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <Button variant="ghost" size="sm" icon={RefreshCw} onClick={load} disabled={loading}>
            Refresh
          </Button>
          <Button
            variant="ghost"
            size="sm"
            icon={visibility === 'shared' ? EyeOff : Eye}
            onClick={handleToggleVisibility}
            disabled={toggling}
          >
            {visibility === 'shared' ? 'Make Private' : 'Share'}
          </Button>
          <Button variant="danger" size="sm" icon={Trash2} onClick={handleDelete} disabled={deleting} isLoading={deleting}>
            Delete
          </Button>
        </div>
      </div>

      {/* Chart body */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading || !data ? (
          <div className="flex items-center justify-center h-64 text-sm text-[var(--text-muted)]">Loading chart...</div>
        ) : data.length === 0 ? (
          <div className="flex items-center justify-center h-64 text-sm text-[var(--text-muted)]">
            No data returned. The underlying query may have expired or returned empty results.
          </div>
        ) : (
          <div className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] p-6">
            <ChartRenderer
              type={chart.chartConfig.type}
              data={data}
              xKey={chart.chartConfig.xKey}
              yKey={chart.chartConfig.yKey}
              seriesKeys={chart.chartConfig.seriesKeys}
              series={chart.chartConfig.series}
              xLabel={chart.chartConfig.xLabel}
              yLabel={chart.chartConfig.yLabel}
              legendPosition={chart.chartConfig.legendPosition}
              height={500}
            />
          </div>
        )}
      </div>
    </div>
  );
}
