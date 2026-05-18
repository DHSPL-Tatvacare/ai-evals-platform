import { useMemo } from 'react';
import { cn } from '@/utils/cn';
import type { ContextWindowInfo } from '../types';

interface ContextProgressPillProps {
  context: ContextWindowInfo | null;
}

/**
 * Slim "context filling" pill rendered in the chat-widget header. Stays
 * hidden until the server-derived ratio crosses
 * ``context.progressStartRatio`` (75% by default), then ticks at
 * ``progressTickRatio`` (10% by default): 75%, 85%, 95%. The pill
 * disappears the turn after compaction fires (tokensUsed resets to 0
 * server-side and ratio drops below the start threshold).
 *
 * ZERO hardcoded numbers — every threshold + tick ratio comes from the
 * backend's ``compaction.py`` via the ``turn_finished`` payload.
 */
export function ContextProgressPill({ context }: ContextProgressPillProps) {
  const display = useMemo(() => {
    if (context === null) return null;
    const { tokensUsed, thresholdTokens, progressStartRatio, progressTickRatio } = context;
    if (thresholdTokens <= 0) return null;
    const ratio = tokensUsed / thresholdTokens;
    if (ratio < progressStartRatio) return null;
    // At or past the threshold → render the explicit 100% / "Full" state.
    // Without this the floor-snap math caps the pill at 95% (start 0.75 +
    // 2 ticks of 0.10 = 0.95) and `atThreshold` never flips true — i.e.
    // the user could never SEE that compaction was due.
    if (ratio >= 1) {
      return { percent: 100, atThreshold: true };
    }
    const tickCount = Math.floor((ratio - progressStartRatio) / progressTickRatio);
    const snapped = progressStartRatio + tickCount * progressTickRatio;
    return {
      percent: Math.round(snapped * 100),
      atThreshold: false,
    };
  }, [context]);

  if (display === null) return null;

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5',
        'font-mono text-[10px] tracking-[0.04em]',
        'border bg-[var(--bg-secondary)]',
        display.atThreshold
          ? 'border-[color-mix(in_srgb,var(--interactive-danger)_50%,transparent)] text-[var(--interactive-danger)]'
          : 'border-[var(--border-default)] text-[var(--text-muted)]',
      )}
      title={
        display.atThreshold
          ? 'Context window full — compaction in progress'
          : 'Context window filling — auto-compaction will trigger at 100%'
      }
      aria-label={`Context window ${display.percent} percent full`}
    >
      <ContextDot full={display.atThreshold} />
      Context {display.percent}%
    </span>
  );
}

function ContextDot({ full }: { full: boolean }) {
  return (
    <span
      className={cn(
        'h-1.5 w-1.5 shrink-0 rounded-full',
        full
          ? 'bg-[var(--interactive-danger)] animate-pulse'
          : 'bg-[var(--text-muted)]',
      )}
      aria-hidden="true"
    />
  );
}
