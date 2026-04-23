import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '@/utils';
import { Button } from './Button';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void; isLoading?: boolean };
  /** Custom content rendered below the description (alternative to `action`) */
  children?: ReactNode;
  className?: string;
  /**
   * Compact variant with smaller icon and less padding — for tables & inline
   * sections. When `compact` is true, the component renders inline (no fill
   * wrapper) even if `fill` is requested.
   */
  compact?: boolean;
  /** Suppress the dashed border wrapper — use when rendered inside another bordered container. */
  bordered?: boolean;
  /**
   * Fill available space and center the state in both axes. Opt-in because
   * most call sites want inline rendering inside their containers.
   *
   * When `fill` is true the wrapper uses `flex-1` (activates inside flex
   * columns) AND a `min-h-[...]` fallback so centering still works even
   * when the ancestor chain does not hand down a bounded height.
   */
  fill?: boolean;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  children,
  className,
  compact,
  bordered = true,
  fill = false,
}: EmptyStateProps) {
  const shouldFill = fill;

  const content = (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-lg',
        bordered && 'border border-dashed border-[var(--border-default)]',
        compact ? 'py-6 px-4' : 'py-10 px-6',
        className,
      )}
    >
      <div
        className={cn(
          'flex items-center justify-center rounded-full bg-[var(--surface-info)]',
          compact ? 'h-10 w-10' : 'h-14 w-14',
        )}
      >
        <Icon className={cn('text-[var(--text-brand)]', compact ? 'h-4 w-4' : 'h-5.5 w-5.5')} />
      </div>
      <div className="text-center space-y-1">
        <p className={cn('font-semibold text-[var(--text-primary)]', compact ? 'text-xs' : 'text-sm')}>
          {title}
        </p>
        {description && (
          <p className={cn('text-[var(--text-secondary)] max-w-sm', compact ? 'text-xs' : 'text-sm')}>
            {description}
          </p>
        )}
      </div>
      {action && (
        <Button
          variant="primary"
          size="sm"
          onClick={action.onClick}
          isLoading={action.isLoading}
        >
          {action.label}
        </Button>
      )}
      {children}
    </div>
  );

  if (shouldFill) {
    // `flex-1` activates when the parent is a flex column that gives us room.
    // The `min-h-[...]` floor is the safety net — centering still works even
    // when the ancestor chain does not hand down a bounded height.
    return (
      <div
        className={cn(
          'flex flex-1 items-center justify-center self-stretch w-full',
          compact ? 'min-h-[200px]' : 'min-h-[360px]',
        )}
      >
        {content}
      </div>
    );
  }

  return content;
}
