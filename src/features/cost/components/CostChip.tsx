/**
 * Compact cost chip shown on eval rows, chat turn footers, report headers,
 * and mini-player items.
 *
 * Two modes:
 *   - inline data (`usage` prop): renders immediately from a `ChipSummary`
 *     payload the caller already has (e.g. chat SSE `done.usage`).
 *   - lookup (`ownerType` + `ownerId`): defers to the module-level batcher,
 *     which coalesces with neighbours to stay inside the fan-out budget.
 *
 * Absence → null render (no layout shift).
 */
import type { ReactNode } from 'react';
import { useChipSummary } from '../hooks/useChipBatcher';
import type { ChipSummary, OwnerType } from '../types';
import { formatTokensCompact, formatUsdCompact } from '../utils/format';

interface CostChipProps {
  usage?: ChipSummary | null;
  ownerType?: OwnerType;
  ownerId?: string | null;
  className?: string;
  prefix?: ReactNode;
  /** Optional override for the tooltip string. Callers with richer context
   *  (chat turn footer, eval detail page) can include extra fields like
   *  cached / reasoning tokens without the chip needing to know the shape. */
  tooltip?: string;
}

export function CostChip({ usage, ownerType, ownerId, className, prefix, tooltip }: CostChipProps) {
  const lookup = useChipSummary(
    usage ? undefined : ownerType,
    usage ? undefined : ownerId,
  );
  const summary: ChipSummary | null = usage ?? lookup.summary;

  if (!summary) return null;
  if (summary.totalTokens === 0 && summary.costUsd === 0 && summary.callCount === 0) return null;

  const derivedTooltip =
    tooltip ??
    [
      `${summary.callCount} call${summary.callCount === 1 ? '' : 's'}`,
      `${summary.totalTokens.toLocaleString('en-US')} tokens`,
    ].join(' · ');

  return (
    <span
      title={derivedTooltip}
      className={
        'inline-flex items-center gap-1 rounded-full bg-[var(--bg-secondary)] px-2 py-0.5 text-[10px] font-normal tracking-normal normal-case tabular-nums text-[var(--text-secondary)] ' +
        (className ?? '')
      }
    >
      {prefix}
      <span>{formatTokensCompact(summary.totalTokens)} tok</span>
      <span className="text-[var(--text-muted)]">·</span>
      <span>{formatUsdCompact(summary.costUsd)}</span>
    </span>
  );
}
