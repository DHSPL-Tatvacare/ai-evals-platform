/**
 * RecordNavigator — shared prev/next control for record detail pages.
 *
 * A compact icon-button pair with an optional "n of N" counter. Designed to
 * sit in a `PageSurface.actions` slot alongside other action buttons. The
 * ordering logic lives in the caller (they know the list the record belongs
 * to); this component just renders + handles input.
 *
 * Optional keyboard shortcuts (`[` prev, `]` next) match common muscle
 * memory from email clients and CRMs. Shortcuts register at the window
 * level and are suppressed while the user is typing in an input.
 *
 * Kept generic — no mention of "lead", "thread", or app names — so any
 * record-detail page can reuse it.
 */

import { useEffect } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Tooltip } from './Tooltip';
import { cn } from '@/utils';

interface RecordNavigatorProps {
  onPrev?: () => void;
  onNext?: () => void;
  /** 1-based index of the current record within its ordered list. */
  current?: number;
  /** Total number of records in the list the caller is navigating. */
  total?: number;
  /** Label for the record type (e.g. "lead", "thread"). Used in aria labels + tooltips. */
  recordLabel?: string;
  /** Disable shortcuts — caller may want to opt out when a modal is open. */
  disableShortcuts?: boolean;
  /** Shortcut keys for prev / next. Defaults match mail/CRM convention. */
  prevKey?: string;
  nextKey?: string;
  className?: string;
}

/** True when keyboard focus is on an element that handles its own typing —
 *  we must not hijack keystrokes in that case. */
function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (target.isContentEditable) return true;
  return false;
}

export function RecordNavigator({
  onPrev,
  onNext,
  current,
  total,
  recordLabel = 'record',
  disableShortcuts = false,
  prevKey = '[',
  nextKey = ']',
  className,
}: RecordNavigatorProps) {
  const canPrev = Boolean(onPrev);
  const canNext = Boolean(onNext);
  const hasCounter = typeof current === 'number' && typeof total === 'number' && total > 0;

  useEffect(() => {
    if (disableShortcuts) return;
    const handler = (event: KeyboardEvent) => {
      if (isTypingTarget(event.target)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === prevKey && canPrev) {
        event.preventDefault();
        onPrev?.();
      } else if (event.key === nextKey && canNext) {
        event.preventDefault();
        onNext?.();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [canPrev, canNext, disableShortcuts, nextKey, onNext, onPrev, prevKey]);

  const prevTip = (
    <span>
      Previous {recordLabel}
      <span className="ml-1 rounded border border-[var(--border-subtle)] px-1 py-px text-[10px] text-[var(--text-muted)]">
        {prevKey}
      </span>
    </span>
  );
  const nextTip = (
    <span>
      Next {recordLabel}
      <span className="ml-1 rounded border border-[var(--border-subtle)] px-1 py-px text-[10px] text-[var(--text-muted)]">
        {nextKey}
      </span>
    </span>
  );

  return (
    <div
      role="group"
      aria-label={`Navigate ${recordLabel}s`}
      className={cn(
        'inline-flex h-8 items-center overflow-hidden rounded-md border border-[var(--border-subtle)] bg-[var(--bg-elevated)]',
        className,
      )}
    >
      <Tooltip content={prevTip} position="bottom">
        <button
          type="button"
          onClick={onPrev}
          disabled={!canPrev}
          aria-label={`Previous ${recordLabel}`}
          className={cn(
            'flex h-8 w-8 items-center justify-center text-[var(--text-secondary)] transition-colors',
            'hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]',
            'disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-[var(--text-secondary)]',
          )}
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
      </Tooltip>

      {hasCounter && (
        <span className="px-2 text-[11px] font-medium tabular-nums text-[var(--text-secondary)] border-x border-[var(--border-subtle)] h-full flex items-center">
          {current}
          <span className="mx-0.5 text-[var(--text-muted)]">/</span>
          {total}
        </span>
      )}

      <Tooltip content={nextTip} position="bottom">
        <button
          type="button"
          onClick={onNext}
          disabled={!canNext}
          aria-label={`Next ${recordLabel}`}
          className={cn(
            'flex h-8 w-8 items-center justify-center text-[var(--text-secondary)] transition-colors',
            'hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]',
            'disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-[var(--text-secondary)]',
          )}
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </Tooltip>
    </div>
  );
}
