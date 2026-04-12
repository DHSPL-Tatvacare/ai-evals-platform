import { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  LineChart, Line, PieChart, Pie, Cell, ResponsiveContainer,
} from 'recharts';
import { resolveColor } from '@/utils/statusColors';

// 8-color palette using CSS variables for theme safety
const CHART_PALETTE = [
  '--color-brand-primary',
  '--color-verdict-pass',
  '--color-level-easy',
  '--color-verdict-soft-fail',
  '--color-level-hard',
  '--color-verdict-fail',
  '--color-level-crack',
  '--color-verdict-critical',
];

interface ChartRendererProps {
  type: 'bar' | 'horizontal_bar' | 'line' | 'pie' | 'stacked_bar';
  data: Record<string, unknown>[];
  xKey: string;
  yKey?: string;
  seriesKeys?: string[];
  xLabel?: string;
  yLabel?: string;
  height?: number;
}

export function ChartRenderer({
  type, data, xKey, yKey, seriesKeys = [], xLabel, yLabel, height = 300,
}: ChartRendererProps) {
  const colors = useMemo(
    () => CHART_PALETTE.map((v) => resolveColor(`var(${v})`)),
    [],
  );

  if (!data.length) {
    return <div className="text-xs text-[var(--text-muted)] py-4 text-center">No data</div>;
  }

  const commonProps = {
    data,
    margin: { top: 8, right: 16, bottom: xLabel ? 24 : 8, left: yLabel ? 32 : 8 },
  };

  if (type === 'pie') {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie
            data={data}
            dataKey={yKey || 'value'}
            nameKey={xKey}
            cx="50%"
            cy="50%"
            outerRadius={height / 3}
            label={({ name, percent }: { name?: string; percent?: number }) => `${name ?? ''} ${((percent ?? 0) * 100).toFixed(0)}%`}
            labelLine={false}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={colors[i % colors.length]} />
            ))}
          </Pie>
          <Tooltip />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    );
  }

  if (type === 'line') {
    const keys = seriesKeys.length ? seriesKeys : yKey ? [yKey] : [];
    return (
      <ResponsiveContainer width="100%" height={height}>
        <LineChart {...commonProps}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
          <XAxis dataKey={xKey} tick={{ fontSize: 10 }} label={xLabel ? { value: xLabel, position: 'bottom', fontSize: 11 } : undefined} />
          <YAxis tick={{ fontSize: 10 }} label={yLabel ? { value: yLabel, angle: -90, position: 'insideLeft', fontSize: 11 } : undefined} />
          <Tooltip contentStyle={{ fontSize: 11, background: 'var(--bg-secondary)', border: '1px solid var(--border-default)' }} />
          <Legend />
          {keys.map((k, i) => (
            <Line key={k} type="monotone" dataKey={k} stroke={colors[i % colors.length]} strokeWidth={2} dot={{ r: 3 }} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    );
  }

  if (type === 'horizontal_bar') {
    return (
      <ResponsiveContainer width="100%" height={Math.max(height, data.length * 32)}>
        <BarChart {...commonProps} layout="vertical">
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
          <XAxis type="number" tick={{ fontSize: 10 }} label={yLabel ? { value: yLabel, position: 'bottom', fontSize: 11 } : undefined} />
          <YAxis type="category" dataKey={xKey} tick={{ fontSize: 10 }} width={120} />
          <Tooltip contentStyle={{ fontSize: 11, background: 'var(--bg-secondary)', border: '1px solid var(--border-default)' }} />
          <Bar dataKey={yKey || 'value'} fill={colors[0]} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    );
  }

  if (type === 'stacked_bar') {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart {...commonProps}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
          <XAxis dataKey={xKey} tick={{ fontSize: 10 }} />
          <YAxis tick={{ fontSize: 10 }} />
          <Tooltip contentStyle={{ fontSize: 11, background: 'var(--bg-secondary)', border: '1px solid var(--border-default)' }} />
          <Legend />
          {seriesKeys.map((k, i) => (
            <Bar key={k} dataKey={k} stackId="stack" fill={colors[i % colors.length]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    );
  }

  // Default: vertical bar
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart {...commonProps}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
        <XAxis dataKey={xKey} tick={{ fontSize: 10 }} label={xLabel ? { value: xLabel, position: 'bottom', fontSize: 11 } : undefined} />
        <YAxis tick={{ fontSize: 10 }} label={yLabel ? { value: yLabel, position: 'insideLeft', angle: -90, fontSize: 11 } : undefined} />
        <Tooltip contentStyle={{ fontSize: 11, background: 'var(--bg-secondary)', border: '1px solid var(--border-default)' }} />
        <Bar dataKey={yKey || 'value'} fill={colors[0]} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
