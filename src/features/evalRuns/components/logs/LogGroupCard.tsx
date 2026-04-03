import type { ReactNode } from 'react';
import { ChevronRight, ChevronDown } from 'lucide-react';

interface LogGroupCardProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  headerLeft: ReactNode;
  headerRight?: ReactNode;
  children: ReactNode;
}

export function LogGroupCard({
  collapsed,
  onToggleCollapse,
  headerLeft,
  headerRight,
  children,
}: LogGroupCardProps) {
  return (
    <div className="rounded-lg border border-[var(--border-default)] overflow-hidden">
      <button
        onClick={onToggleCollapse}
        className="w-full flex items-center gap-3 px-4 py-2.5 bg-[var(--bg-secondary)]/60 hover:bg-[var(--bg-secondary)] transition-colors text-left"
      >
        {collapsed ? (
          <ChevronRight className="h-4 w-4 text-[var(--text-muted)] shrink-0" />
        ) : (
          <ChevronDown className="h-4 w-4 text-[var(--text-muted)] shrink-0" />
        )}

        <div className="flex items-center gap-2 min-w-0 flex-1">
          {headerLeft}
        </div>

        {headerRight && (
          <div className="flex items-center gap-3 shrink-0">
            {headerRight}
          </div>
        )}
      </button>

      {!collapsed && (
        <div className="border-t border-[var(--border-subtle)]">
          <div className="space-y-px">
            {children}
          </div>
        </div>
      )}
    </div>
  );
}
