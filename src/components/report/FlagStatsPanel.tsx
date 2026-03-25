import { cn } from '@/utils/cn';

interface BehavioralFlag {
  key: string;
  label: string;
  relevant: number;
  notRelevant: number;
  present: number;
  color?: string;
}

interface OutcomeFlag {
  key: string;
  label: string;
  relevant: number;
  notRelevant: number;
  attempted: number;
  accepted?: number;
  total: number;
}

interface Props {
  behavioralFlags?: BehavioralFlag[];
  outcomeFlags?: OutcomeFlag[];
  className?: string;
}

export function FlagStatsPanel({ behavioralFlags, outcomeFlags, className }: Props) {
  return (
    <div className={cn('space-y-6', className)}>
      {behavioralFlags && behavioralFlags.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold mb-3">Behavioral Flags</h4>
          <div className="grid grid-cols-3 gap-3">
            {behavioralFlags.map((f) => (
              <div key={f.key} className="bg-[var(--bg-primary)] p-3.5 rounded-lg border border-[var(--border)]">
                <div className="text-[11px] uppercase text-[var(--text-secondary)]">{f.label}</div>
                <div className="flex items-baseline gap-1.5 mt-1">
                  <span className={cn('text-2xl font-bold', f.color || 'text-[var(--color-error)]')}>{f.present}</span>
                  <span className="text-xs text-[var(--text-secondary)]">of {f.relevant} relevant</span>
                </div>
                <div className="text-[11px] text-[var(--text-secondary)] mt-1">
                  {f.notRelevant} calls — not relevant
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {outcomeFlags && outcomeFlags.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold mb-3">Outcome Flags</h4>
          <div className="grid grid-cols-4 gap-3">
            {outcomeFlags.map((f) => {
              const reachPct = f.total > 0 ? ((f.relevant / f.total) * 100).toFixed(0) : '0';
              const convPct = f.relevant > 0 ? ((f.attempted / f.relevant) * 100).toFixed(0) : '0';
              return (
                <div key={f.key} className="bg-[var(--bg-primary)] p-3.5 rounded-lg border border-[var(--border)]">
                  <div className="text-[11px] uppercase text-[var(--text-secondary)]">{f.label}</div>
                  <div className="text-2xl font-bold text-[var(--accent)] mt-1">{f.attempted}</div>
                  <div className="text-[11px] text-[var(--text-secondary)]">
                    Reach: {f.relevant}/{f.total} ({reachPct}%)
                  </div>
                  <div className="text-[11px] font-semibold text-[var(--accent)]">
                    Conv: {f.attempted}/{f.relevant} ({convPct}%)
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
