import type { CrossRunStats } from '@/types/crossRunAnalytics';
import { METRIC_COLOR } from '../report/shared/colors';
import MetricInfo from '../MetricInfo';

/** Convert camelCase key to display label (e.g. intentAccuracy → Intent Accuracy). */
function formatBreakdownKey(key: string): string {
  return key
    .replace(/([A-Z])/g, ' $1')
    .replace(/_/g, ' ')
    .replace(/^\s/, '')
    .split(' ')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

/** Convert camelCase breakdown key to snake_case metric key for MetricInfo lookup. */
function breakdownMetricKey(key: string): string {
  return key.replace(/([A-Z])/g, '_$1').toLowerCase();
}

interface Props {
  stats: CrossRunStats;
}

function StatCard({
  label,
  value,
  subtitle,
  color,
  metricKey,
}: {
  label: string;
  value: string | number;
  subtitle?: string;
  color?: string;
  metricKey?: string;
}) {
  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded px-4 py-3">
      <div className="flex items-center gap-1">
        <p className="text-xs uppercase tracking-wider text-[var(--text-muted)] font-semibold">
          {label}
        </p>
        {metricKey && <MetricInfo metricKey={metricKey} />}
      </div>
      <p
        className="text-xl font-extrabold mt-0.5 leading-tight"
        style={{ color: color || 'var(--text-primary)' }}
      >
        {value}
      </p>
      {subtitle && (
        <p className="text-[10px] text-[var(--text-muted)] mt-0.5">{subtitle}</p>
      )}
    </div>
  );
}

export default function StatCardsRow({ stats }: Props) {
  return (
    <div className="space-y-3">
      {/* Row 1: Fixed cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          label="Runs Analyzed"
          value={stats.totalRuns}
          subtitle={`${stats.totalRuns} of ${stats.allRuns} runs have reports`}
          metricKey="cross_runs_analyzed"
        />
        <StatCard
          label="Thread Evaluations"
          value={stats.totalThreads}
          metricKey="cross_thread_evaluations"
        />
        <StatCard
          label="Avg Health Score"
          value={`${stats.avgHealthScore.toFixed(1)} (${stats.avgGrade})`}
          color={METRIC_COLOR(stats.avgHealthScore)}
          metricKey="cross_avg_health_score"
        />
        <StatCard
          label="Adversarial Pass Rate"
          value={stats.adversarialPassRate != null ? `${stats.adversarialPassRate.toFixed(1)}%` : '\u2014'}
          subtitle={stats.adversarialPassRate == null ? 'No adversarial runs' : undefined}
          color={stats.adversarialPassRate != null ? METRIC_COLOR(stats.adversarialPassRate) : undefined}
          metricKey="cross_adversarial_pass_rate"
        />
      </div>

      {/* Row 2: Dynamic breakdown cards — use existing metric definitions where available */}
      {Object.keys(stats.avgBreakdown).length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {Object.entries(stats.avgBreakdown).map(([key, value]) => (
            <StatCard
              key={key}
              label={formatBreakdownKey(key)}
              value={`${value.toFixed(1)}%`}
              color={METRIC_COLOR(value)}
              metricKey={breakdownMetricKey(key)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
