import { AlertTriangle, CircleAlert, Coins, Hash, Sigma } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Card } from '@/components/ui';
import type { CostKpi } from '../types';
import { formatInt, formatTokensCompact, formatUsd } from '../utils/format';

interface CostKpiRowProps {
  kpis: CostKpi;
}

export function CostKpiRow({ kpis }: CostKpiRowProps) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
      <KpiCard icon={Coins} label="Total spend" value={formatUsd(kpis.totalCostUsd)} />
      <KpiCard icon={Sigma} label="Total tokens" value={formatTokensCompact(kpis.totalTokens)} />
      <KpiCard icon={Hash} label="Calls" value={formatInt(kpis.totalCalls)} />
      <KpiCard icon={CircleAlert} label="Errors" value={formatInt(kpis.errorCalls)} tone={kpis.errorCalls > 0 ? 'danger' : 'neutral'} />
      <KpiCard icon={AlertTriangle} label="Unpriced" value={formatInt(kpis.pricingFallbackCalls)} tone={kpis.pricingFallbackCalls > 0 ? 'warning' : 'neutral'} />
    </div>
  );
}

function KpiCard({
  icon: Icon,
  label,
  value,
  tone = 'neutral',
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  tone?: 'neutral' | 'danger' | 'warning';
}) {
  const colorClass =
    tone === 'danger'
      ? 'text-[var(--color-error)]'
      : tone === 'warning'
        ? 'text-[var(--color-warning)]'
        : 'text-[var(--text-primary)]';
  return (
    <Card className="p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">{label}</p>
          <p className={`mt-1 text-xl font-semibold tabular-nums ${colorClass}`}>{value}</p>
        </div>
        <Icon className="h-4 w-4 text-[var(--text-muted)]" />
      </div>
    </Card>
  );
}
