import { cn } from '@/utils/cn';

interface Props {
  label: string;
  value: string | number;
  suffix?: string;
  color: string;
  weight?: string;
  progressValue?: number;
  className?: string;
}

export default function MetricCard({ label, value, suffix, color, weight, progressValue, className }: Props) {
  return (
    <div className={cn(
      'bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-lg overflow-hidden text-center',
      className,
    )}>
      <div className="h-1" style={{ backgroundColor: color }} />
      <div className="p-4">
        <div className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-2">
          {label}
        </div>
        <div className="text-2xl font-bold" style={{ color }}>
          {value}{suffix}
        </div>
        {progressValue != null && (
          <div className="mt-3 h-1.5 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{ width: `${Math.min(progressValue, 100)}%`, backgroundColor: color }}
            />
          </div>
        )}
        {weight && (
          <div className="text-xs text-[var(--text-muted)] mt-2">Weight: {weight}</div>
        )}
      </div>
    </div>
  );
}
