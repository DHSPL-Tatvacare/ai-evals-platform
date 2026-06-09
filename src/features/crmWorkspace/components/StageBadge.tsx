import { cn } from '@/utils';

const STAGE_COLORS: Record<string, string> = {
  'new lead': 'bg-[var(--bg-secondary)] text-[var(--text-muted)]',
  'call back': 'bg-[var(--surface-accent-amber)] text-[var(--color-accent-amber)]',
  'rnr': 'bg-[var(--surface-accent-orange)] text-[var(--color-accent-orange)]',
  'interested in future plan': 'bg-[var(--surface-accent-blue)] text-[var(--color-accent-blue)]',
  'not interested': 'bg-[var(--surface-error)] text-[var(--color-error)]',
  'converted': 'bg-[var(--surface-success)] text-[var(--color-success)]',
  'invalid / junk': 'bg-[var(--bg-secondary)] text-[var(--text-muted)]',
  're-enquired': 'bg-[var(--surface-accent-purple)] text-[var(--color-accent-purple)]',
};

/** Pill badge showing a lead's CRM stage. */
export function StageBadge({ stage, truncate = true }: { stage: string; truncate?: boolean }) {
  const key = stage.toLowerCase();
  const colorClass = STAGE_COLORS[key] ?? 'bg-[var(--bg-secondary)] text-[var(--text-muted)]';
  // Shorten "Interested In Future Plan" → "Interested" in compact contexts
  const label = truncate ? (stage.replace(/in future plan/i, '').trim() || stage) : stage;
  return (
    <span className={cn('inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium', colorClass)}>
      {label}
    </span>
  );
}
