import { useState } from 'react';
import { Plus, Check } from 'lucide-react';
import { cn } from '@/utils/cn';
import { ChartRenderer } from '@/features/analytics/components/ChartRenderer';
import { analyticsLibraryApi } from '@/services/api/analyticsLibraryApi';
import { notificationService } from '@/services/notifications';
import type { ChartData } from './types';

interface ChatChartProps {
  chart: ChartData;
  appId: string;
}

export function ChatChart({ chart, appId }: ChatChartProps) {
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await analyticsLibraryApi.saveChart({
        appId,
        title: chart.spec.title,
        sqlQuery: chart.sqlQuery,
        chartConfig: {
          type: chart.spec.type,
          xKey: chart.spec.xKey,
          yKey: chart.spec.yKey,
          seriesKeys: chart.spec.seriesKeys,
          xLabel: chart.spec.xLabel,
          yLabel: chart.spec.yLabel,
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

  return (
    <div className="mt-2 rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-[var(--text-primary)]">{chart.spec.title}</span>
        <button
          onClick={handleSave}
          disabled={saved || saving}
          className={cn(
            'inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-medium transition-colors',
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
        type={chart.spec.type}
        data={chart.data as Record<string, unknown>[]}
        xKey={chart.spec.xKey}
        yKey={chart.spec.yKey}
        seriesKeys={chart.spec.seriesKeys}
        xLabel={chart.spec.xLabel}
        yLabel={chart.spec.yLabel}
        height={220}
      />
    </div>
  );
}
