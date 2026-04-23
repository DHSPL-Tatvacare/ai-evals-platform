/**
 * SectionBlock — titled content block with no filled background.
 *
 * Replaces the ad-hoc `rounded-lg border bg-[var(--bg-secondary)] p-4` pattern
 * that accumulated across record-detail pages. Uses a small uppercase header,
 * an optional tone-tinted icon chip, and an optional hairline divider instead
 * of a gray card, so multiple sections can stack without turning the page
 * into a field of boxes.
 *
 * `tone` maps to an existing design-system colour token — never hardcoded —
 * and also gates a subtle gradient background when `surface="tinted"` is set,
 * for sections that deserve a bit of visual weight (e.g. a "Plan Purchased"
 * success highlight on a converted lead).
 *
 * Kept generic (no CRM or app vocabulary) — consumed by the shared
 * `RecordWorkspace` primitive and any other record-detail page.
 */

import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/utils';

export type SectionBlockTone = 'neutral' | 'brand' | 'success' | 'warning' | 'info';
export type SectionBlockSurface = 'transparent' | 'tinted' | 'outlined';

interface SectionBlockProps {
  /** Uppercase eyebrow label shown above the content. */
  title?: string;
  /** Optional icon shown in a tone-tinted chip on the left of the header. */
  icon?: LucideIcon;
  /** Tone anchors the icon chip colour (and tinted surface if enabled). */
  tone?: SectionBlockTone;
  /** Visual weight of the section's own surface. */
  surface?: SectionBlockSurface;
  /** Optional trailing node in the header row (e.g. an action button). */
  headerTrailing?: ReactNode;
  /** Content. */
  children: ReactNode;
  /** Render a hairline under the header (default off). */
  divider?: boolean;
  /** Extra class on the outer wrapper. */
  className?: string;
  /** Extra class on the body wrapper (the bit that holds the children). */
  bodyClassName?: string;
}

const TONE_CHIP_CLASSES: Record<SectionBlockTone, string> = {
  neutral: 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)] ring-[var(--border-subtle)]',
  brand:
    'bg-[var(--surface-brand-subtle)] text-[var(--text-brand)] ring-[var(--border-brand)]/60',
  success:
    'bg-[color-mix(in_srgb,var(--color-success)_15%,transparent)] text-[var(--color-success)] ring-[color-mix(in_srgb,var(--color-success)_35%,transparent)]',
  warning:
    'bg-[color-mix(in_srgb,var(--color-warning)_15%,transparent)] text-[var(--color-warning)] ring-[color-mix(in_srgb,var(--color-warning)_35%,transparent)]',
  info:
    'bg-[color-mix(in_srgb,var(--color-info)_15%,transparent)] text-[var(--color-info)] ring-[color-mix(in_srgb,var(--color-info)_35%,transparent)]',
};

/** Soft tone gradient used when `surface="tinted"`. Anchors on the same token
 *  family as the icon chip so tone stays visually coherent. */
const TONE_SURFACE_STYLE: Record<SectionBlockTone, string> = {
  neutral:
    'bg-[linear-gradient(180deg,var(--bg-elevated)_0%,var(--bg-secondary)_100%)] border border-[var(--border-subtle)]',
  brand:
    'bg-[linear-gradient(180deg,var(--surface-brand-subtle)_0%,transparent_100%)] border border-[var(--border-brand)]/35',
  success:
    'bg-[linear-gradient(180deg,color-mix(in_srgb,var(--color-success)_10%,transparent)_0%,transparent_100%)] border border-[color-mix(in_srgb,var(--color-success)_25%,transparent)]',
  warning:
    'bg-[linear-gradient(180deg,color-mix(in_srgb,var(--color-warning)_10%,transparent)_0%,transparent_100%)] border border-[color-mix(in_srgb,var(--color-warning)_25%,transparent)]',
  info:
    'bg-[linear-gradient(180deg,color-mix(in_srgb,var(--color-info)_10%,transparent)_0%,transparent_100%)] border border-[color-mix(in_srgb,var(--color-info)_25%,transparent)]',
};

export function SectionBlock({
  title,
  icon: Icon,
  tone = 'neutral',
  surface = 'transparent',
  headerTrailing,
  children,
  divider = false,
  className,
  bodyClassName,
}: SectionBlockProps) {
  const surfaceClasses =
    surface === 'tinted'
      ? cn('rounded-xl p-4', TONE_SURFACE_STYLE[tone])
      : surface === 'outlined'
        ? 'rounded-xl border border-[var(--border-subtle)] p-4'
        : '';

  return (
    <section className={cn('flex flex-col', surfaceClasses, className)}>
      {(title || headerTrailing || Icon) && (
        <div
          className={cn(
            'flex items-center justify-between gap-3',
            divider ? 'mb-3 pb-2 border-b border-[var(--border-subtle)]' : 'mb-3',
          )}
        >
          <div className="flex min-w-0 items-center gap-2">
            {Icon && (
              <span
                className={cn(
                  'flex h-6 w-6 items-center justify-center rounded-md ring-1',
                  TONE_CHIP_CLASSES[tone],
                )}
                aria-hidden
              >
                <Icon className="h-3.5 w-3.5" />
              </span>
            )}
            {title && (
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                {title}
              </p>
            )}
          </div>
          {headerTrailing && <div className="flex items-center gap-2">{headerTrailing}</div>}
        </div>
      )}
      <div className={cn('flex flex-col', bodyClassName)}>{children}</div>
    </section>
  );
}
