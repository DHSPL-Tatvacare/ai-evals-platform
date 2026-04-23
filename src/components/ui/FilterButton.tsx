import { Filter } from 'lucide-react';
import { cn } from '@/utils';
import { Button } from './Button';

interface FilterButtonProps {
  activeCount: number;
  onClick: () => void;
  label?: string;
  className?: string;
  iconOnly?: boolean;
}

export function FilterButton({
  activeCount,
  onClick,
  label = 'Filters',
  className,
  iconOnly = false,
}: FilterButtonProps) {
  if (iconOnly) {
    return (
      <div className={cn('relative', className)}>
        <Button
          variant="secondary"
          size="sm"
          icon={Filter}
          iconOnly
          onClick={onClick}
          aria-label={label}
          title={label}
        />
        {activeCount > 0 && (
          <span className="pointer-events-none absolute -right-1 -top-1 inline-flex min-w-[16px] items-center justify-center rounded-full bg-[var(--interactive-primary)] px-1 text-[10px] font-semibold leading-4 text-[var(--text-on-color)]">
            {activeCount}
          </span>
        )}
      </div>
    );
  }

  return (
    <Button
      variant="secondary"
      size="sm"
      icon={Filter}
      onClick={onClick}
      className={cn('relative', className)}
    >
      <span className="inline-flex items-center gap-1.5">
        {label}
        {activeCount > 0 && (
          <span className="inline-flex min-w-[18px] items-center justify-center rounded-full bg-[var(--interactive-primary)] px-1.5 text-[10px] font-semibold text-[var(--text-on-color)]">
            {activeCount}
          </span>
        )}
      </span>
    </Button>
  );
}
