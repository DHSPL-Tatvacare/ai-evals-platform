import { type InputHTMLAttributes, type ReactNode, forwardRef } from 'react';
import { cn } from '@/utils';

interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size'> {
  icon?: React.ReactNode;
  rightSlot?: ReactNode;
  error?: string;
  /** Matches Combobox sizing so inline field rows line up. Defaults to md (h-9). */
  size?: 'sm' | 'md';
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, icon, rightSlot, error, type, size = 'md', ...props }, ref) => {
    const sizeStyles = size === 'sm' ? 'h-7 px-2.5 text-[13px]' : 'h-9 px-3 text-[14px]';
    return (
      <div className="relative">
        {icon && (
          <div className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]">
            {icon}
          </div>
        )}
        <input
          type={type}
          ref={ref}
          className={cn(
            'w-full rounded-[6px] border bg-[var(--bg-primary)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] transition-colors',
            sizeStyles,
            'border-[var(--border-default)] focus:border-[var(--border-focus)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-accent)]/50',
            'disabled:cursor-not-allowed disabled:opacity-50',
            icon && 'pl-10',
            rightSlot && 'pr-12',
            error && 'border-[var(--color-error)] focus:border-[var(--color-error)] focus:ring-[var(--color-error)]/50',
            className
          )}
          {...props}
        />
        {rightSlot && (
          <div className="absolute right-2 top-1/2 -translate-y-1/2">
            {rightSlot}
          </div>
        )}
        {error && (
          <p className="mt-1 text-[11px] text-[var(--color-error)]">{error}</p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';
