import { CheckCircle, Circle, AlertCircle, Loader2, Send, Undo2 } from 'lucide-react';
import { Badge, Button } from '@/components/ui';
import type { HumanReview, OverallVerdict } from '@/types';

interface HumanReviewStatusProps {
  humanReview: HumanReview | null;
  isDirty: boolean;
  isSubmitting: boolean;
  reviewedCount: number;
  totalItems: number;
  overallVerdict: OverallVerdict | null;
  onSubmit: () => void;
  onDiscard: () => void;
}

const VERDICT_LABEL: Record<OverallVerdict, string> = {
  accepted: 'Accepted',
  rejected: 'Rejected',
  accepted_with_corrections: 'Corrections',
};

const VERDICT_VARIANT: Record<OverallVerdict, 'success' | 'error' | 'warning'> = {
  accepted: 'success',
  rejected: 'error',
  accepted_with_corrections: 'warning',
};

export function HumanReviewStatus({
  humanReview,
  isDirty,
  isSubmitting,
  reviewedCount,
  totalItems,
  overallVerdict,
  onSubmit,
  onDiscard,
}: HumanReviewStatusProps) {
  const hasSaved = !!humanReview;
  const progressPct = totalItems > 0 ? (reviewedCount / totalItems) * 100 : 0;
  const canSubmit = isDirty || !hasSaved;

  return (
    <div className="flex items-center gap-3 px-4 py-2 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-subtle)] shrink-0">
      {/* Status indicator */}
      {hasSaved && !isDirty ? (
        <CheckCircle className="h-3.5 w-3.5 text-[var(--color-success)] shrink-0" />
      ) : isDirty ? (
        <AlertCircle className="h-3.5 w-3.5 text-[var(--color-warning)] shrink-0" />
      ) : (
        <Circle className="h-3.5 w-3.5 text-[var(--text-muted)] shrink-0" />
      )}

      {/* Progress: count + inline bar */}
      <div className="flex items-center gap-2">
        <span className="text-[12px] font-medium text-[var(--text-secondary)] tabular-nums">
          {reviewedCount}/{totalItems}
        </span>
        <div className="w-16 h-1.5 rounded-full bg-[var(--bg-tertiary)]">
          <div
            className="h-full rounded-full bg-[var(--color-brand-primary)] transition-all"
            style={{ width: `${Math.min(progressPct, 100)}%` }}
          />
        </div>
      </div>

      {/* Verdict badge — only after at least one review */}
      {overallVerdict && (
        <Badge variant={VERDICT_VARIANT[overallVerdict]} className="text-[10px]">
          {VERDICT_LABEL[overallVerdict]}
        </Badge>
      )}

      {/* Dirty hint (subtle text, not a full badge) */}
      {isDirty && hasSaved && (
        <span className="text-[10px] text-[var(--color-warning)]">unsaved</span>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Timestamp — subtle, right-aligned */}
      {hasSaved && !isDirty && humanReview?.completedAt && (
        <span className="text-[10px] text-[var(--text-muted)]">
          {new Date(humanReview.completedAt).toLocaleString()}
        </span>
      )}

      {/* Discard */}
      {isDirty && (
        <Button variant="ghost" size="sm" onClick={onDiscard} className="h-7 gap-1 text-[12px]">
          <Undo2 className="h-3 w-3" />
          Discard
        </Button>
      )}

      {/* Submit / Update */}
      <Button
        size="sm"
        onClick={onSubmit}
        disabled={isSubmitting || !canSubmit}
        className="h-7 gap-1 text-[12px]"
      >
        {isSubmitting ? (
          <Loader2 className="h-3 w-3 animate-spin" />
        ) : (
          <Send className="h-3 w-3" />
        )}
        {hasSaved ? 'Update' : 'Submit'}
      </Button>
    </div>
  );
}
