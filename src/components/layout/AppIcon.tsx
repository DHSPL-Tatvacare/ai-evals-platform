import { ShieldAlert } from 'lucide-react';
import { cn } from '@/utils';

export type AppIconKind = 'image' | 'glyph';

interface AppIconProps {
  /** ``'image'`` renders the URL in ``value``; ``'glyph'`` renders the
   *  matching lucide icon (currently only ``shield-alert`` for admin). */
  iconType: AppIconKind;
  iconValue: string;
  name: string;
  /** Tailwind sizing/spacing/colour overrides applied to the wrapper. */
  className?: string;
}

/**
 * Single source of truth for rendering the icon of an app (or the admin
 * surface). Used by ``AppSwitcher`` for both its trigger and dropdown rows,
 * and by the collapsed ``Sidebar`` header. New icon kinds (e.g. an inline
 * SVG component) extend this one switch instead of being scattered across
 * call sites.
 */
export function AppIcon({ iconType, iconValue, name, className }: AppIconProps) {
  if (iconType === 'image') {
    return (
      <img
        src={iconValue}
        alt={name}
        className={cn('rounded object-cover', className)}
      />
    );
  }
  return (
    <div
      className={cn(
        'flex items-center justify-center rounded border border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]',
        className,
      )}
      aria-label={name}
    >
      <ShieldAlert className="h-4 w-4" />
    </div>
  );
}
