import { Badge, VisibilityBadge } from '@/components/ui';
import type { AssetVisibility } from '@/types';

interface OwnershipBannerProps {
  title: string;
  visibility: AssetVisibility;
  ownerLabel: string;
  updatedLabel?: string;
  mode: 'read-only' | 'editable';
  helperText: string;
}

export function OwnershipBanner({
  title,
  visibility,
  ownerLabel,
  updatedLabel,
  mode,
  helperText,
}: OwnershipBannerProps) {
  return (
    <div className="rounded-[8px] border border-[var(--border-default)] bg-[var(--bg-secondary)]/40 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-[var(--text-primary)]">{title}</span>
        <VisibilityBadge visibility={visibility} compact />
        <Badge variant={mode === 'editable' ? 'success' : 'neutral'} size="sm">
          {mode === 'editable' ? 'Editable' : 'Read only'}
        </Badge>
      </div>
      <p className="mt-2 text-xs text-[var(--text-secondary)]">
        {helperText}
      </p>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-[var(--text-muted)]">
        <span>Owner: {ownerLabel}</span>
        {updatedLabel ? <span>Updated: {updatedLabel}</span> : null}
      </div>
    </div>
  );
}
