import { Info, CheckCircle2, AlertTriangle, XCircle, Search, Lightbulb } from 'lucide-react';
import { cn } from '@/utils/cn';

type Variant = 'info' | 'success' | 'warning' | 'danger' | 'insight' | 'suggest';

interface Props {
  variant: Variant;
  title?: string;
  children: React.ReactNode;
  className?: string;
}

const VARIANT_CONFIG: Record<Variant, { border: string; bg: string; icon: React.ElementType }> = {
  info: { border: 'var(--color-info)', bg: 'bg-[var(--surface-info)]', icon: Info },
  success: { border: 'var(--color-success)', bg: 'bg-[var(--surface-success)]', icon: CheckCircle2 },
  warning: { border: 'var(--color-warning)', bg: 'bg-[var(--surface-warning)]', icon: AlertTriangle },
  danger: { border: 'var(--color-error)', bg: 'bg-[var(--surface-error)]', icon: XCircle },
  insight: { border: 'var(--color-info)', bg: 'bg-[var(--surface-info)]', icon: Search },
  suggest: { border: 'var(--color-accent-purple)', bg: 'bg-[var(--surface-info)]', icon: Lightbulb },
};

export default function CalloutBox({ variant, title, children, className }: Props) {
  const config = VARIANT_CONFIG[variant];
  const Icon = config.icon;

  return (
    <div
      className={cn('border-l-[3px] rounded-r-lg px-4 py-3', config.bg, className)}
      style={{ borderLeftColor: config.border }}
    >
      {title && (
        <div className="flex items-center gap-1.5 mb-1">
          <Icon className="h-3.5 w-3.5 shrink-0 text-[var(--text-secondary)]" />
          <span className="font-semibold text-sm text-[var(--text-primary)]">{title}</span>
        </div>
      )}
      <div className="text-sm leading-relaxed text-[var(--text-secondary)]">{children}</div>
    </div>
  );
}
