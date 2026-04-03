import type { ReactNode } from 'react';
import { ChevronUp, ChevronDown } from 'lucide-react';
import { cn } from '@/utils';

type AccentColor = 'success' | 'error' | 'warning' | 'info' | 'neutral';

interface LogRowShellProps {
  expanded: boolean;
  onToggle: () => void;
  nested?: boolean;
  accentColor: AccentColor;
  summaryLeft: ReactNode;
  summaryRight: ReactNode;
  children: ReactNode;
}

const accentMap: Record<AccentColor, string> = {
  success: 'border-l-[var(--color-success)]',
  error: 'border-l-[var(--color-error)]',
  warning: 'border-l-[var(--color-warning)]',
  info: 'border-l-[var(--color-info)]',
  neutral: 'border-l-[var(--text-muted)]',
};

export function LogRowShell({
  expanded,
  onToggle,
  nested = false,
  accentColor,
  summaryLeft,
  summaryRight,
  children,
}: LogRowShellProps) {
  const borderColor = accentMap[accentColor];
  const outerClass = nested
    ? cn('border-l-[3px]', borderColor)
    : cn('bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-md overflow-hidden border-l-[3px]', borderColor);

  return (
    <div className={outerClass}>
      <button
        onClick={onToggle}
        className="w-full flex items-start justify-between gap-3 px-3 py-2 text-left hover:bg-[var(--bg-secondary)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-accent)]"
      >
        <div className="flex flex-col gap-0.5 min-w-0 flex-1">
          {summaryLeft}
        </div>
        <div className="flex items-center gap-2 shrink-0 mt-0.5">
          {summaryRight}
          {expanded ? (
            <ChevronUp className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5 text-[var(--text-tertiary)]" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-[var(--border-subtle)] px-3 py-3 space-y-3">
          {children}
        </div>
      )}
    </div>
  );
}
