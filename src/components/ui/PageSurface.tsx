import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/utils';

interface PageSurfaceProps {
  icon: LucideIcon;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  filters?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function PageSurface({
  icon: Icon,
  title,
  subtitle,
  actions,
  filters,
  children,
  className,
}: PageSurfaceProps) {
  const hasRightSlot = Boolean(filters || actions);

  return (
    <div
      className={cn(
        'flex h-full flex-col overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)]',
        className,
      )}
    >
      <div className="flex items-center justify-between gap-4 border-b border-dashed border-[var(--border-subtle)] px-5 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <Icon className="h-4 w-4 shrink-0 text-[var(--text-secondary)]" aria-hidden />
          <div className="min-w-0">
            <h1 className="truncate text-[15px] font-semibold leading-tight text-[var(--text-primary)]">
              {title}
            </h1>
            {subtitle && (
              <p className="mt-0.5 truncate text-xs text-[var(--text-secondary)]">
                {subtitle}
              </p>
            )}
          </div>
        </div>
        {hasRightSlot && (
          <div className="flex flex-shrink-0 flex-wrap items-center justify-end gap-2">
            {filters}
            {actions}
          </div>
        )}
      </div>
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-5 py-4">
        {children}
      </div>
    </div>
  );
}
