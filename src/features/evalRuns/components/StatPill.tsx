import type { ReactNode } from 'react';
import MetricInfo from './MetricInfo';

interface StatPillProps {
  label: string;
  value: ReactNode;
  metricKey?: string;
  color?: string;
}

export function StatPill({ label, value, metricKey, color }: StatPillProps) {
  const valueStyle = color ? { color } : undefined;

  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded px-3 py-2">
      <div className="flex items-center gap-1">
        <p className="text-xs uppercase tracking-wider text-[var(--text-muted)] font-semibold">{label}</p>
        {metricKey && <MetricInfo metricKey={metricKey} />}
      </div>
      <p
        className={`text-lg font-bold mt-0.5 leading-tight${color ? '' : ' text-[var(--text-primary)]'}`}
        style={valueStyle}
      >
        {value}
      </p>
    </div>
  );
}
