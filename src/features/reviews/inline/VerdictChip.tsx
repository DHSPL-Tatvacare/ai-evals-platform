import type { ReactNode } from 'react';
import { BeforeAfterChip } from './BeforeAfterChip';
import type { LabelCategory } from '@/config/labelDefinitions';
import { getLabelDefinition } from '@/config/labelDefinitions';
import { cn } from '@/utils/cn';

export interface VerdictChipProps {
  /** AI-assigned verdict (the original value). */
  aiVerdict: string | null | undefined;
  /** Reviewer's override. When equal to `aiVerdict` or nullish, renders as a plain badge. */
  humanVerdict?: string | null;
  /** Label category used to resolve display name + color. */
  category: LabelCategory;
  /** Chip size (applies in both states). */
  size?: 'sm' | 'md';
  /**
   * Optional custom renderer for the plain (non-overridden) badge. Use this when
   * the surface needs a non-default badge shape (e.g. `SeverityBadge`, custom
   * "Pass/Fail" pill). When omitted, a category-colored pill is used.
   */
  renderBadge?: (value: string | null | undefined) => ReactNode;
}

/**
 * Unified "AI verdict vs human override" display.
 *
 * Shows a struck-through AI value + colored override value when an override is
 * present. Otherwise renders a plain badge for the AI verdict. This is the
 * single abstraction every review-aware surface should use — do not reach for
 * `<BeforeAfterChip>` directly from feature code.
 */
export function VerdictChip({
  aiVerdict,
  humanVerdict,
  category,
  size = 'sm',
  renderBadge,
}: VerdictChipProps) {
  const aiValue = aiVerdict ?? '';
  const humanValue = humanVerdict ?? null;
  const isOverridden = !!humanValue && humanValue !== aiValue;

  if (isOverridden) {
    return (
      <BeforeAfterChip
        before={aiValue || '—'}
        after={humanValue}
        category={category}
        size={size}
      />
    );
  }

  if (renderBadge) {
    return <>{renderBadge(aiVerdict)}</>;
  }

  return <DefaultBadge value={aiValue} category={category} size={size} />;
}

function DefaultBadge({
  value,
  category,
  size,
}: {
  value: string;
  category: LabelCategory;
  size: 'sm' | 'md';
}) {
  const def = getLabelDefinition(value, category);
  const textSize = size === 'sm' ? 'text-[9px]' : 'text-[10px]';
  const padding = size === 'sm' ? 'py-px px-1.5' : 'py-0.5 px-2';
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full font-semibold text-white',
        textSize,
        padding,
      )}
      style={{ backgroundColor: def.color }}
    >
      {def.displayName || value || '—'}
    </span>
  );
}
