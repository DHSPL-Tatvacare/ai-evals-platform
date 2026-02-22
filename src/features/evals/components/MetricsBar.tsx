import { Sparkles } from 'lucide-react';
import { MetricCard } from './MetricCard';
import type { MetricResult } from '../metrics';

interface MetricsBarProps {
  metrics: MetricResult[] | null;
}

export function MetricsBar({ metrics }: MetricsBarProps) {
  if (!metrics || metrics.length === 0) {
    return (
      <div className="mt-3 flex items-center gap-2">
        <div className="flex items-center gap-3 rounded-lg border border-dashed border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3">
          <Sparkles className="h-4 w-4 text-[var(--text-muted)]" />
          <span className="text-[12px] text-[var(--text-muted)]">
            Run AI Evaluation to see metrics
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="mt-3 flex items-center gap-3">
      <div
        className="grid gap-2"
        style={{
          gridTemplateColumns: `repeat(${metrics.length}, minmax(0, 1fr))`,
          minWidth: `${metrics.length * 120}px`,
        }}
      >
        {metrics.map(metric => (
          <MetricCard key={metric.id} metric={metric} compact />
        ))}
      </div>
    </div>
  );
}
