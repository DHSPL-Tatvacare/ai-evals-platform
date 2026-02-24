import { Sparkles, Bot, UserCheck } from 'lucide-react';
import { MetricCard } from './MetricCard';
import { Tooltip } from '@/components/ui';
import { cn } from '@/utils/cn';
import type { MetricResult } from '../metrics';

interface MetricsBarProps {
  metrics: MetricResult[] | null;
  /** When true, shows the AI/Human source toggle */
  hasHumanReview?: boolean;
  /** Current metrics source */
  metricsSource?: 'ai' | 'human';
  /** Callback when source toggles */
  onMetricsSourceChange?: (source: 'ai' | 'human') => void;
}

export function MetricsBar({
  metrics,
  hasHumanReview,
  metricsSource = 'ai',
  onMetricsSourceChange,
}: MetricsBarProps) {
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

  const showToggle = hasHumanReview && !!onMetricsSourceChange;

  return (
    <div className="mt-3 flex items-center gap-3">
      {/* Metrics grid — flex-1 so toggle stays anchored right */}
      <div className="flex-1 min-w-0">
        <div
          className="grid gap-2"
          style={{
            gridTemplateColumns: `repeat(${metrics.length}, minmax(0, 1fr))`,
          }}
        >
          {metrics.map(metric => (
            <MetricCard key={metric.id} metric={metric} compact />
          ))}
        </div>
      </div>

      {/* Compact icon toggle — only when human review exists */}
      {showToggle && (
        <MetricsSourceToggle
          metricsSource={metricsSource}
          onMetricsSourceChange={onMetricsSourceChange}
        />
      )}
    </div>
  );
}

/** Compact icon-based toggle for switching between AI and Human metrics */
function MetricsSourceToggle({
  metricsSource,
  onMetricsSourceChange,
}: {
  metricsSource: 'ai' | 'human';
  onMetricsSourceChange: (source: 'ai' | 'human') => void;
}) {
  return (
    <div className="flex items-center gap-0.5 p-0.5 rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] shrink-0">
      <Tooltip content="AI-computed metrics" position="bottom">
        <button
          type="button"
          onClick={() => onMetricsSourceChange('ai')}
          className={cn(
            'p-1.5 rounded-md transition-all',
            metricsSource === 'ai'
              ? 'bg-[var(--bg-brand)] text-[var(--text-on-brand)] shadow-sm'
              : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]',
          )}
          aria-label="Show AI-computed metrics"
        >
          <Bot className="h-3.5 w-3.5" />
        </button>
      </Tooltip>
      <Tooltip content="Human-reviewed metrics" position="bottom">
        <button
          type="button"
          onClick={() => onMetricsSourceChange('human')}
          className={cn(
            'p-1.5 rounded-md transition-all',
            metricsSource === 'human'
              ? 'bg-[var(--bg-brand)] text-[var(--text-on-brand)] shadow-sm'
              : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]',
          )}
          aria-label="Show human-reviewed metrics"
        >
          <UserCheck className="h-3.5 w-3.5" />
        </button>
      </Tooltip>
    </div>
  );
}
