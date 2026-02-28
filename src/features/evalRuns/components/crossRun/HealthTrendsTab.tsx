import { useMemo } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts';
import { TrendingUp } from 'lucide-react';
import type { HealthTrendPoint, CrossRunStats } from '@/types/crossRunAnalytics';
import { EmptyState } from '@/components/ui';
import { METRIC_HEX } from '../report/shared/colors';
import { useResolvedColor } from '@/hooks/useResolvedColor';
import { resolveColor } from '@/utils/statusColors';
import SectionHeader from '../report/shared/SectionHeader';

/** Convert camelCase key to display label. */
function formatKey(key: string): string {
  return key
    .replace(/([A-Z])/g, ' $1')
    .replace(/_/g, ' ')
    .replace(/^\s/, '')
    .split(' ')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

/** Palette for breakdown lines — resolved from design system accent tokens. */
const LINE_COLOR_VARS = [
  'var(--color-accent-indigo)',
  'var(--color-accent-amber)',
  'var(--color-accent-teal)',
  'var(--color-accent-rose)',
  'var(--color-accent-purple)',
  'var(--color-accent-pink)',
  'var(--color-accent-cyan)',
];

interface Props {
  trend: HealthTrendPoint[];
  stats: CrossRunStats;
}

export default function HealthTrendsTab({ trend, stats }: Props) {
  const gridColor = useResolvedColor('var(--border-subtle)');
  const textColor = useResolvedColor('var(--text-muted)');

  // Discover all unique breakdown keys across all trend points
  const breakdownKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const pt of trend) {
      for (const k of Object.keys(pt.breakdown)) {
        keys.add(k);
      }
    }
    return Array.from(keys);
  }, [trend]);

  // Build chart data
  const chartData = useMemo(() => {
    return trend.map((pt) => {
      const dateStr = pt.createdAt
        ? new Date(pt.createdAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
        : '';
      const entry: Record<string, string | number> = {
        name: pt.runName || pt.runId.slice(0, 8),
        date: dateStr,
        'Health Score': pt.healthScore,
      };
      for (const key of breakdownKeys) {
        entry[formatKey(key)] = pt.breakdown[key] ?? 0;
      }
      return entry;
    });
  }, [trend, breakdownKeys]);

  if (trend.length === 0) {
    return (
      <EmptyState
        icon={TrendingUp}
        title="No trend data"
        description="No runs with generated reports found."
        compact
      />
    );
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Health Score Trend"
        description="Overall health score and per-dimension breakdown across evaluation runs."
      />

      <div className="bg-[var(--bg-primary)] rounded border border-[var(--border-subtle)] p-3">
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: textColor }}
            />
            <YAxis
              domain={[0, 100]}
              tick={{ fontSize: 10, fill: textColor }}
            />
            <RechartsTooltip
              contentStyle={{
                fontSize: 12,
                backgroundColor: 'var(--bg-elevated)',
                border: '1px solid var(--border-default)',
                color: 'var(--text-primary)',
              }}
              labelFormatter={(_label, payload) => {
                if (payload?.[0]?.payload) {
                  return payload[0].payload.name as string;
                }
                return '';
              }}
            />
            <Legend iconSize={8} wrapperStyle={{ fontSize: 11 }} />
            <ReferenceLine
              y={80}
              stroke={gridColor}
              strokeDasharray="6 3"
              label={{ value: 'B+', position: 'insideTopRight', fontSize: 9, fill: textColor }}
            />

            {/* Overall health score — bold primary line */}
            <Line
              type="monotone"
              dataKey="Health Score"
              stroke={METRIC_HEX(stats.avgHealthScore)}
              strokeWidth={2.5}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
            />

            {/* Dynamic breakdown dimension lines */}
            {breakdownKeys.map((key, idx) => (
              <Line
                key={key}
                type="monotone"
                dataKey={formatKey(key)}
                stroke={resolveColor(LINE_COLOR_VARS[idx % LINE_COLOR_VARS.length])}
                strokeWidth={1.5}
                strokeDasharray="4 2"
                dot={{ r: 2 }}
                activeDot={{ r: 4 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
