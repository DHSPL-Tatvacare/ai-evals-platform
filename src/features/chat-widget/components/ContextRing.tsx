/** Composer context gauge: a ring that fills as supervisor context grows toward
 *  the compaction threshold, spins while compacting, and explains itself on hover.
 *  Pure-derived from the part stream (no new store / no new wire frame). */
import { selectSessionParts, useStreamStore } from '@/features/sherlock/streamStore';
import { deriveContextUsage } from '@/features/sherlock/contextUsage';

import { useChatWidgetStore } from '../useChatWidget';

const R = 7;
const CIRC = 2 * Math.PI * R;

function formatTokens(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

export function ContextRing() {
  const sessionId = useChatWidgetStore((s) => s.sessionId);
  const parts = useStreamStore(selectSessionParts(sessionId ?? ''));
  const { tokensUsed, threshold, compacting } = deriveContextUsage(parts);

  if (compacting) {
    return (
      <span
        className="inline-flex h-[18px] w-[18px] shrink-0 items-center justify-center"
        title="Compacting context…"
        aria-label="Compacting context"
        data-testid="context-ring"
        data-state="compacting"
      >
        <svg className="h-[18px] w-[18px] animate-spin" viewBox="0 0 18 18">
          <circle cx="9" cy="9" r={R} fill="none" stroke="var(--border-default)" strokeWidth="2" />
          <circle
            cx="9"
            cy="9"
            r={R}
            fill="none"
            stroke="var(--color-brand-primary)"
            strokeWidth="2"
            strokeLinecap="round"
            strokeDasharray={`${CIRC * 0.25} ${CIRC}`}
          />
        </svg>
      </span>
    );
  }

  if (tokensUsed == null || threshold == null || threshold <= 0) return null;

  const pct = Math.min(1, tokensUsed / threshold);
  const near = pct >= 0.85;
  const stroke = near ? 'var(--color-warning)' : 'var(--text-muted)';
  const pctUntil = Math.max(0, Math.round((1 - pct) * 100));

  return (
    <span
      className="group relative inline-flex h-[18px] w-[18px] shrink-0 items-center justify-center"
      aria-label={`Context ${Math.round(pct * 100)}% used`}
      data-testid="context-ring"
      data-state="idle"
    >
      <svg className="h-[18px] w-[18px] -rotate-90" viewBox="0 0 18 18">
        <circle cx="9" cy="9" r={R} fill="none" stroke="var(--border-default)" strokeWidth="2" />
        <circle
          cx="9"
          cy="9"
          r={R}
          fill="none"
          stroke={stroke}
          strokeWidth="2"
          strokeLinecap="round"
          strokeDasharray={CIRC}
          strokeDashoffset={CIRC * (1 - pct)}
          className="transition-[stroke-dashoffset] duration-500"
        />
      </svg>
      <span className="pointer-events-none absolute bottom-full right-0 z-[var(--z-popover)] mb-1.5 hidden w-max max-w-[200px] rounded-md border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2 py-1.5 text-[11px] leading-relaxed shadow-[var(--shadow-md)] group-hover:block">
        <span className="block font-medium text-[var(--text-primary)]">
          Context {formatTokens(tokensUsed)} / {formatTokens(threshold)}
        </span>
        <span className="block text-[var(--text-muted)]">{pctUntil}% until compaction</span>
      </span>
    </span>
  );
}
