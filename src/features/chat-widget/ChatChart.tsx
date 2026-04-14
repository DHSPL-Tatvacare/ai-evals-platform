import { useMemo, useState } from 'react';
import { Plus, Check } from 'lucide-react';
import { cn } from '@/utils/cn';
import { ChartRenderer } from '@/features/analytics/components/ChartRenderer';
import { analyticsLibraryApi } from '@/services/api/analyticsLibraryApi';
import { notificationService } from '@/services/notifications';
import type { ChartData } from './types';

/** Chart type display labels for suggestion pills. */
const TYPE_LABELS: Record<string, string> = {
  bar: 'Bar',
  horizontal_bar: 'H. Bar',
  stacked_bar: 'Stacked',
  grouped_bar: 'Grouped',
  line: 'Line',
  area: 'Area',
  stacked_area: 'Stacked Area',
  pie: 'Pie',
  donut: 'Donut',
  scatter: 'Scatter',
  radar: 'Radar',
  funnel: 'Funnel',
  treemap: 'Treemap',
  radial_bar: 'Radial',
  composed: 'Composed',
};

/** Max items before tail entries are grouped into "Other". */
const CONSOLIDATION_LIMITS: Record<string, number> = {
  pie: 8,
  donut: 8,
  radar: 10,
  radial_bar: 8,
  treemap: 20,
};

function resolveChartHeight(type: string, dataCount: number): number {
  switch (type) {
    case 'pie':
    case 'donut':
    case 'treemap':
    case 'radial_bar':
      return 240;
    case 'radar':
      return 260;
    case 'horizontal_bar':
      return Math.max(200, Math.min(dataCount * 28, 400));
    case 'funnel':
      return Math.max(180, Math.min(dataCount * 36, 360));
    default:
      return 220;
  }
}

function consolidateData(
  data: Record<string, unknown>[],
  type: string,
  xKey: string,
  yKey: string | undefined,
): Record<string, unknown>[] {
  const maxSlices = CONSOLIDATION_LIMITS[type];
  if (!maxSlices || data.length <= maxSlices) return data;

  const valueKey = yKey || 'value';
  const sorted = [...data].sort((a, b) => Number(b[valueKey] ?? 0) - Number(a[valueKey] ?? 0));
  const top = sorted.slice(0, maxSlices - 1);
  const rest = sorted.slice(maxSlices - 1);

  if (rest.length === 0) return top;

  const otherValue = rest.reduce((sum, row) => sum + Number(row[valueKey] ?? 0), 0);
  return [...top, { [xKey]: `Other (${rest.length})`, [valueKey]: otherValue }];
}

interface ChatChartProps {
  chart: ChartData;
  appId: string;
}

export function ChatChart({ chart, appId }: ChatChartProps) {
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [activeType, setActiveType] = useState(chart.spec.type);

  const handleSave = async () => {
    setSaving(true);
    try {
      await analyticsLibraryApi.saveChart({
        appId,
        title: chart.spec.title,
        sqlQuery: chart.sqlQuery,
        chartConfig: {
          type: activeType,
          xKey: chart.spec.xKey,
          yKey: chart.spec.yKey,
          seriesKeys: chart.spec.seriesKeys,
          series: chart.spec.series,
          xLabel: chart.spec.xLabel,
          yLabel: chart.spec.yLabel,
          legendPosition: chart.spec.legendPosition,
        },
        sourceQuestion: chart.sourceQuestion,
      });
      setSaved(true);
      notificationService.success('Chart added to library');
    } catch {
      notificationService.error('Failed to save chart');
    } finally {
      setSaving(false);
    }
  };

  const displayData = useMemo(
    () => consolidateData(
      chart.data as Record<string, unknown>[],
      activeType,
      chart.spec.xKey,
      chart.spec.yKey,
    ),
    [chart.data, activeType, chart.spec.xKey, chart.spec.yKey],
  );

  const height = resolveChartHeight(activeType, displayData.length);
  const alternatives = chart.spec.alternatives ?? [];

  return (
    <div className="mt-2 rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-[var(--text-primary)] truncate mr-2">{chart.spec.title}</span>
        <button
          onClick={handleSave}
          disabled={saved || saving}
          className={cn(
            'inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-medium transition-colors shrink-0',
            saved
              ? 'bg-[var(--color-verdict-pass)]/10 text-[var(--color-verdict-pass)]'
              : 'bg-[var(--color-brand-accent)] text-[var(--color-brand-primary)] hover:bg-[var(--color-brand-primary)] hover:text-white',
          )}
        >
          {saved ? <Check className="h-2.5 w-2.5" /> : <Plus className="h-2.5 w-2.5" />}
          {saved ? 'Saved' : 'Add to library'}
        </button>
      </div>
      <ChartRenderer
        type={activeType}
        data={displayData}
        xKey={chart.spec.xKey}
        yKey={chart.spec.yKey}
        seriesKeys={chart.spec.seriesKeys}
        series={chart.spec.series}
        xLabel={chart.spec.xLabel}
        yLabel={chart.spec.yLabel}
        legendPosition={chart.spec.legendPosition}
        height={height}
        compact
      />
      {alternatives.length > 0 && (
        <div className="mt-2 flex items-center gap-1.5">
          <span className="text-[10px] text-[var(--text-muted)]">Try as:</span>
          {alternatives.map((alt) => (
            <button
              key={alt}
              onClick={() => setActiveType(alt)}
              className={cn(
                'rounded px-2 py-0.5 text-[10px] font-medium transition-colors',
                activeType === alt
                  ? 'border border-[var(--color-brand-primary)] bg-[var(--color-brand-primary)]/10 text-[var(--color-brand-primary)]'
                  : 'bg-[var(--bg-secondary)] text-[var(--text-muted)] hover:text-[var(--text-secondary)]',
              )}
            >
              {TYPE_LABELS[alt] || alt}
            </button>
          ))}
          {activeType !== chart.spec.type && (
            <button
              onClick={() => setActiveType(chart.spec.type)}
              className="rounded px-2 py-0.5 text-[10px] font-medium bg-[var(--bg-secondary)] text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
            >
              {TYPE_LABELS[chart.spec.type] || chart.spec.type}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
