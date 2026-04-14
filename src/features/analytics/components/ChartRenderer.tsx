import { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  LineChart, Line, PieChart, Pie, Cell, ResponsiveContainer,
  AreaChart, Area, RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ScatterChart, Scatter, FunnelChart, Funnel, Treemap,
  RadialBarChart, RadialBar, ComposedChart,
} from 'recharts';
import { resolveColor } from '@/utils/statusColors';
import type { SeriesConfig } from '@/features/chat-widget/types';

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

interface ChartMapping {
  cartesian?: boolean;
  polar?: boolean;
  layoutVertical?: boolean;
  stacked?: boolean;
  innerRadius?: number;
}

const CHART_MAP: Record<string, ChartMapping> = {
  bar:            { cartesian: true },
  horizontal_bar: { cartesian: true, layoutVertical: true },
  stacked_bar:    { cartesian: true, stacked: true },
  grouped_bar:    { cartesian: true },
  line:           { cartesian: true },
  area:           { cartesian: true },
  stacked_area:   { cartesian: true, stacked: true },
  scatter:        { cartesian: true },
  radar:          { polar: true },
  funnel:         {},
  treemap:        {},
  radial_bar:     { polar: true },
  composed:       { cartesian: true },
  pie:            { polar: true },
  donut:          { polar: true, innerRadius: 0.5 },
};

interface ChartRendererProps {
  type: string;
  data: Record<string, unknown>[];
  xKey: string;
  yKey?: string;
  seriesKeys?: string[];
  series?: SeriesConfig[];
  xLabel?: string;
  yLabel?: string;
  legendPosition?: 'top' | 'bottom' | 'right' | 'none';
  height?: number;
  compact?: boolean;
}

function truncateLabel(value: string, maxLen: number): string {
  if (value.length <= maxLen) return value;
  return value.slice(0, maxLen - 1) + '\u2026';
}

export function ChartRenderer({
  type, data, xKey, yKey, seriesKeys = [], series, xLabel, yLabel,
  legendPosition, height = 300, compact = false,
}: ChartRendererProps) {
  const colors = useMemo(
    () => CHART_PALETTE.map((v) => resolveColor(`var(${v})`)),
    [],
  );

  if (!data.length) {
    return <div className="text-xs text-[var(--text-muted)] py-4 text-center">No data</div>;
  }

  const mapping = CHART_MAP[type] ?? CHART_MAP.bar;
  const labelMaxLen = compact ? 18 : 40;
  const tickFontSize = compact ? 9 : 10;
  const shouldShowLegend = legendPosition !== 'none';
  const legendPos = legendPosition ?? (mapping.polar ? 'right' : 'bottom');
  const xTickFormatter = compact ? (v: string) => truncateLabel(String(v), labelMaxLen) : undefined;
  const autoRotate = compact && data.length > 8;
  const tooltipStyle = { fontSize: compact ? 10 : 11, background: 'var(--bg-secondary)', border: '1px solid var(--border-default)' };
  const commonMargin = compact
    ? { top: 4, right: 8, bottom: xLabel || autoRotate ? 24 : 4, left: yLabel ? 28 : 4 }
    : { top: 8, right: 16, bottom: xLabel ? 24 : 8, left: yLabel ? 32 : 8 };

  const legendProps = shouldShowLegend ? {
    layout: (legendPos === 'right' ? 'vertical' : 'horizontal') as 'vertical' | 'horizontal',
    align: (legendPos === 'right' ? 'right' : 'center') as 'right' | 'center',
    verticalAlign: (legendPos === 'top' ? 'top' : legendPos === 'right' ? 'middle' : 'bottom') as 'top' | 'middle' | 'bottom',
    wrapperStyle: compact ? { fontSize: 10, maxHeight: height - 16, overflowY: 'auto' as const } : undefined,
    formatter: (value: string) => truncateLabel(value, labelMaxLen),
  } : undefined;

  // ── Pie / Donut ──────────────────────────────────────────────
  if (type === 'pie' || type === 'donut') {
    const outerRadius = compact ? Math.min(height / 3, 80) : height / 3;
    const innerRadius = mapping.innerRadius ? outerRadius * mapping.innerRadius : 0;
    return (
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie
            data={data}
            dataKey={yKey || 'value'}
            nameKey={xKey}
            cx="50%"
            cy="50%"
            outerRadius={outerRadius}
            innerRadius={innerRadius}
            label={compact ? undefined : ({ name, percent }: { name?: string; percent?: number }) =>
              `${name ?? ''} ${((percent ?? 0) * 100).toFixed(0)}%`
            }
            labelLine={false}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={colors[i % colors.length]} />
            ))}
          </Pie>
          <Tooltip contentStyle={tooltipStyle} formatter={(value: number | undefined) => (value ?? 0).toLocaleString()} />
          {legendProps && <Legend {...legendProps} />}
        </PieChart>
      </ResponsiveContainer>
    );
  }

  // ── Radar ────────────────────────────────────────────────────
  if (type === 'radar') {
    const keys = seriesKeys.length ? seriesKeys : yKey ? [yKey] : [];
    return (
      <ResponsiveContainer width="100%" height={height}>
        <RadarChart data={data} cx="50%" cy="50%" outerRadius={compact ? '70%' : '80%'}>
          <PolarGrid stroke="var(--border-subtle)" />
          <PolarAngleAxis dataKey={xKey} tick={{ fontSize: tickFontSize }} />
          <PolarRadiusAxis tick={{ fontSize: tickFontSize - 1 }} />
          {keys.map((k, i) => (
            <Radar key={k} dataKey={k} stroke={colors[i % colors.length]} fill={colors[i % colors.length]} fillOpacity={0.3} />
          ))}
          <Tooltip contentStyle={tooltipStyle} />
          {legendProps && <Legend {...legendProps} />}
        </RadarChart>
      </ResponsiveContainer>
    );
  }

  // ── Radial Bar ───────────────────────────────────────────────
  if (type === 'radial_bar') {
    const coloredData = data.map((d, i) => ({ ...d, fill: colors[i % colors.length] }));
    return (
      <ResponsiveContainer width="100%" height={height}>
        <RadialBarChart data={coloredData} innerRadius="20%" outerRadius="90%" startAngle={180} endAngle={0}>
          <RadialBar dataKey={yKey || 'value'} background={{ fill: 'var(--bg-secondary)' }} />
          <Tooltip contentStyle={tooltipStyle} />
          {legendProps && <Legend {...legendProps} iconType="circle" formatter={(_, entry) => truncateLabel(String((entry as { payload?: Record<string, unknown> }).payload?.[xKey] ?? ''), labelMaxLen)} />}
        </RadialBarChart>
      </ResponsiveContainer>
    );
  }

  // ── Funnel ───────────────────────────────────────────────────
  if (type === 'funnel') {
    const coloredData = data.map((d, i) => ({ ...d, fill: colors[i % colors.length] }));
    return (
      <ResponsiveContainer width="100%" height={height}>
        <FunnelChart>
          <Tooltip contentStyle={tooltipStyle} />
          <Funnel dataKey={yKey || 'value'} nameKey={xKey} data={coloredData} />
          {legendProps && <Legend {...legendProps} />}
        </FunnelChart>
      </ResponsiveContainer>
    );
  }

  // ── Treemap ──────────────────────────────────────────────────
  if (type === 'treemap') {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <Treemap
          data={data.map((d, i) => ({ name: String(d[xKey] ?? ''), size: Number(d[yKey || 'value'] ?? 0), fill: colors[i % colors.length] }))}
          dataKey="size"
          nameKey="name"
          aspectRatio={4 / 3}
          stroke="var(--bg-primary)"
        />
      </ResponsiveContainer>
    );
  }

  // ── Scatter ──────────────────────────────────────────────────
  if (type === 'scatter') {
    const numericCols = seriesKeys.length ? seriesKeys : yKey ? [yKey] : [];
    const scatterYKey = numericCols[0];
    if (!scatterYKey) return <div className="text-xs text-[var(--text-muted)] py-4 text-center">Scatter needs two numeric columns</div>;
    return (
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart margin={commonMargin}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
          <XAxis dataKey={xKey} type="number" tick={{ fontSize: tickFontSize }} name={xLabel || xKey} label={xLabel ? { value: xLabel, position: 'bottom', fontSize: tickFontSize + 1 } : undefined} />
          <YAxis dataKey={scatterYKey} type="number" tick={{ fontSize: tickFontSize }} name={yLabel || scatterYKey} label={yLabel ? { value: yLabel, angle: -90, position: 'insideLeft', fontSize: tickFontSize + 1 } : undefined} />
          <Tooltip contentStyle={tooltipStyle} cursor={{ strokeDasharray: '3 3' }} />
          <Scatter data={data} fill={colors[0]} />
        </ScatterChart>
      </ResponsiveContainer>
    );
  }

  // ── Composed ─────────────────────────────────────────────────
  if (type === 'composed' && series?.length) {
    const visualMap: Record<string, typeof Bar | typeof Line | typeof Area | typeof Scatter> = {
      bar: Bar, line: Line, area: Area, scatter: Scatter,
    };
    return (
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={data} margin={commonMargin}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
          <XAxis dataKey={xKey} tick={{ fontSize: tickFontSize }} tickFormatter={xTickFormatter} label={xLabel ? { value: xLabel, position: 'bottom', fontSize: tickFontSize + 1 } : undefined} />
          <YAxis tick={{ fontSize: tickFontSize }} label={yLabel ? { value: yLabel, angle: -90, position: 'insideLeft', fontSize: tickFontSize + 1 } : undefined} />
          <Tooltip contentStyle={tooltipStyle} />
          {legendProps && <Legend {...legendProps} />}
          {series.map((s, i) => {
            const Visual = visualMap[s.type] ?? Bar;
            const key = s.dataKey;
            const color = colors[i % colors.length];
            if (Visual === Line) return <Line key={key} dataKey={key} stroke={color} strokeWidth={2} dot={{ r: compact ? 2 : 3 }} />;
            if (Visual === Area) return <Area key={key} dataKey={key} stroke={color} fill={color} fillOpacity={0.3} />;
            if (Visual === Scatter) return <Scatter key={key} dataKey={key} fill={color} />;
            return <Bar key={key} dataKey={key} fill={color} stackId={s.stackId} radius={[4, 4, 0, 0]} />;
          })}
        </ComposedChart>
      </ResponsiveContainer>
    );
  }

  // ── Cartesian (bar, horizontal_bar, stacked_bar, grouped_bar, line, area, stacked_area) ──
  const isVerticalLayout = mapping.layoutVertical;
  const yAxisWidth = compact ? 90 : 120;

  if (type === 'line' || type === 'area') {
    const keys = seriesKeys.length ? seriesKeys : yKey ? [yKey] : [];
    const ChartContainer = type === 'area' ? AreaChart : LineChart;
    return (
      <ResponsiveContainer width="100%" height={height}>
        <ChartContainer data={data} margin={commonMargin}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
          <XAxis dataKey={xKey} tick={{ fontSize: tickFontSize }} tickFormatter={xTickFormatter} angle={autoRotate ? -45 : 0} textAnchor={autoRotate ? 'end' : 'middle'} label={xLabel ? { value: xLabel, position: 'bottom', fontSize: tickFontSize + 1 } : undefined} />
          <YAxis tick={{ fontSize: tickFontSize }} label={yLabel ? { value: yLabel, angle: -90, position: 'insideLeft', fontSize: tickFontSize + 1 } : undefined} />
          <Tooltip contentStyle={tooltipStyle} />
          {legendProps && !compact && <Legend {...legendProps} />}
          {keys.map((k, i) => (
            type === 'area'
              ? <Area key={k} type="monotone" dataKey={k} stroke={colors[i % colors.length]} fill={colors[i % colors.length]} fillOpacity={0.3} stackId={mapping.stacked ? 'stack' : undefined} />
              : <Line key={k} type="monotone" dataKey={k} stroke={colors[i % colors.length]} strokeWidth={2} dot={{ r: compact ? 2 : 3 }} />
          ))}
        </ChartContainer>
      </ResponsiveContainer>
    );
  }

  // Bar variants (bar, horizontal_bar, stacked_bar, grouped_bar)
  const barKeys = seriesKeys.length ? seriesKeys : yKey ? [yKey] : [];
  const barHeight = compact ? 24 : 32;
  const resolvedHeight = isVerticalLayout ? Math.max(height, data.length * barHeight) : height;

  return (
    <ResponsiveContainer width="100%" height={resolvedHeight}>
      <BarChart data={data} margin={commonMargin} layout={isVerticalLayout ? 'vertical' : 'horizontal'}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
        {isVerticalLayout ? (
          <>
            <XAxis type="number" tick={{ fontSize: tickFontSize }} label={yLabel ? { value: yLabel, position: 'bottom', fontSize: tickFontSize + 1 } : undefined} />
            <YAxis type="category" dataKey={xKey} tick={{ fontSize: tickFontSize }} width={yAxisWidth} tickFormatter={(v: string) => truncateLabel(String(v), compact ? 14 : 20)} />
          </>
        ) : (
          <>
            <XAxis dataKey={xKey} tick={{ fontSize: tickFontSize }} tickFormatter={xTickFormatter} angle={autoRotate ? -45 : 0} textAnchor={autoRotate ? 'end' : 'middle'} label={xLabel ? { value: xLabel, position: 'bottom', fontSize: tickFontSize + 1 } : undefined} />
            <YAxis tick={{ fontSize: tickFontSize }} label={yLabel ? { value: yLabel, position: 'insideLeft', angle: -90, fontSize: tickFontSize + 1 } : undefined} />
          </>
        )}
        <Tooltip contentStyle={tooltipStyle} />
        {legendProps && barKeys.length > 1 && <Legend {...legendProps} />}
        {barKeys.map((k, i) => (
          <Bar key={k} dataKey={k} fill={colors[i % colors.length]} stackId={mapping.stacked ? 'stack' : undefined} radius={isVerticalLayout ? [0, 4, 4, 0] : [4, 4, 0, 0]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
