import { useEffect, useMemo, useState } from 'react';
import { LayoutDashboard } from 'lucide-react';
import { Button } from '@/components/ui';
import { analyticsLibraryApi } from '@/services/api/analyticsLibraryApi';
import { notificationService } from '@/services/notifications';
import { analyticsDashboardForApp } from '@/config/routes';
import type { ChartPart, SaveToastPart } from '../types';

interface DashboardBarProps {
  appId: string;
  sessionId: string | null;
  charts: ChartPart[];
  defaultTitle?: string;
  onSaved?: (toast: SaveToastPart) => void;
}

function chartPreviewBars(index: number): number[] {
  return [30 + index * 8, 50 + index * 6, 42 + index * 7, 66 + index * 5];
}

export function DashboardBar({
  appId,
  sessionId,
  charts,
  defaultTitle,
  onSaved,
}: DashboardBarProps) {
  const [title, setTitle] = useState(defaultTitle ?? 'Untitled dashboard');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (defaultTitle) {
      setTitle(defaultTitle);
    }
  }, [defaultTitle]);

  const uniqueCharts = useMemo(() => {
    const seen = new Set<string>();
    return charts.filter((chart) => {
      const key = chart.chartId ?? `${chart.spec.title}:${chart.sqlQuery}`;
      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
  }, [charts]);

  if (uniqueCharts.length < 2) {
    return null;
  }

  const handleCreate = async () => {
    if (saving) {
      return;
    }

    setSaving(true);
    try {
      const chartIds: string[] = [];

      for (const chart of uniqueCharts) {
        if (chart.chartId) {
          chartIds.push(chart.chartId);
          continue;
        }

        const savedChart = await analyticsLibraryApi.saveChart({
          appId,
          title: chart.spec.title,
          sqlQuery: chart.sqlQuery,
          chartConfig: {
            type: chart.spec.type,
            xKey: chart.spec.xKey,
            yKey: chart.spec.yKey,
            seriesKeys: chart.spec.seriesKeys,
            series: chart.spec.series,
            xLabel: chart.spec.xLabel,
            yLabel: chart.spec.yLabel,
            legendPosition: chart.spec.legendPosition,
          },
          sourceQuestion: chart.sourceQuestion,
          sourceSessionId: sessionId ?? undefined,
        });
        chartIds.push(savedChart.id);
      }

      const dashboard = await analyticsLibraryApi.saveDashboard({
        appId,
        title: title.trim() || 'Untitled dashboard',
        chartIds,
        sourceSessionId: sessionId ?? undefined,
      });

      onSaved?.({
        type: 'save-toast',
        variant: 'dashboard',
        title: 'Dashboard created',
        subtitle: title.trim() || 'Untitled dashboard',
        linkText: 'Open',
        linkHref: analyticsDashboardForApp(appId, dashboard.id),
      });
      notificationService.success('Dashboard created');
    } catch (error) {
      notificationService.error(error instanceof Error ? error.message : 'Failed to create dashboard');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-2xl border border-[var(--border-default)] bg-[var(--bg-secondary)]">
      <div className="flex items-center justify-between gap-3 border-b border-[var(--border-default)] px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
            <LayoutDashboard className="h-4 w-4 text-[var(--text-brand)]" />
            <span>Create dashboard</span>
          </div>
          <div className="mt-1 text-xs text-[var(--text-muted)]">
            {`${uniqueCharts.length} charts ready to group`}
          </div>
        </div>
      </div>
      <div className="flex gap-2 overflow-x-auto px-4 py-3">
        {uniqueCharts.map((chart, index) => (
          <div key={`${chart.chartId ?? chart.sqlQuery}-${index}`} className="min-w-[120px] rounded-xl border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2">
            <div className="truncate text-[11px] font-medium text-[var(--text-primary)]">{chart.spec.title}</div>
            <div className="mt-2 flex h-12 items-end gap-1">
              {chartPreviewBars(index).map((height, barIndex) => (
                <span
                  key={`${barIndex}-${height}`}
                  className="w-3 rounded-t bg-[var(--interactive-primary)]/70"
                  style={{ height }}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-2 border-t border-[var(--border-default)] px-4 py-3">
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="Dashboard name"
          className="flex-1 rounded-xl border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none transition-colors focus:border-[var(--border-brand)]"
        />
        <Button variant="primary" size="sm" onClick={() => void handleCreate()} disabled={saving}>
          {saving ? 'Creating…' : 'Create'}
        </Button>
      </div>
    </div>
  );
}
