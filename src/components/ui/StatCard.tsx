import type { LucideIcon } from 'lucide-react';
import { Card } from './Card';
import { cn } from '@/utils/cn';

export type StatCardTone = 'neutral' | 'danger' | 'warning' | 'positive';

interface StatCardProps {
  icon: LucideIcon;
  label: string;
  value: string;
  hint?: string;
  tone?: StatCardTone;
}

const TONE_CLASS: Record<StatCardTone, string> = {
  neutral: 'text-[var(--text-primary)]',
  danger: 'text-[var(--color-error)]',
  warning: 'text-[var(--color-warning)]',
  positive: 'text-[var(--color-success)]',
};

/** Compact KPI tile. Shares the cost KPI-row grammar so every metric tile on
 *  the platform reads the same. */
export function StatCard({ icon: Icon, label, value, hint, tone = 'neutral' }: StatCardProps) {
  return (
    <Card className="p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">{label}</p>
          <p className={cn('mt-1 text-xl font-semibold tabular-nums', TONE_CLASS[tone])}>{value}</p>
          {hint && <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">{hint}</p>}
        </div>
        <Icon className="h-4 w-4 shrink-0 text-[var(--text-muted)]" />
      </div>
    </Card>
  );
}
