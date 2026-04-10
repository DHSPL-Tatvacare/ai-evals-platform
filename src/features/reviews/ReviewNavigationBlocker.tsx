import { useEffect, useCallback } from 'react';
import { useBlocker } from 'react-router-dom';
import { ConfirmDialog } from '@/components/ui';
import { useReviewModeStore } from '@/stores/reviewModeStore';

function isAllowedPath(pathname: string, runId: string | null): boolean {
  if (runId && pathname.includes(`/runs/${runId}`)) return true;
  if (pathname.includes('/threads/')) return true;
  return false;
}

export function ReviewNavigationBlocker() {
  const active = useReviewModeStore((s) => s.active);
  const runId = useReviewModeStore((s) => s.runId);
  const saveDraft = useReviewModeStore((s) => s.saveDraft);
  const discardDraft = useReviewModeStore((s) => s.discardDraft);

  const blocker = useBlocker(({ nextLocation }) => {
    if (!active) return false;
    return !isAllowedPath(nextLocation.pathname, runId);
  });

  // Block browser close / refresh
  const handleBeforeUnload = useCallback(
    (e: BeforeUnloadEvent) => {
      if (!active) return;
      e.preventDefault();
    },
    [active],
  );

  useEffect(() => {
    if (!active) return;
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [active, handleBeforeUnload]);

  const handleDiscard = async () => {
    await discardDraft();
    blocker.proceed?.();
  };

  const handleSaveAndLeave = async () => {
    await saveDraft();
    // After saving, exit review and proceed
    useReviewModeStore.getState().exitReview();
    blocker.proceed?.();
  };

  return (
    <ConfirmDialog
      isOpen={blocker.state === 'blocked'}
      onClose={() => blocker.reset?.()}
      onConfirm={handleDiscard}
      title="Leave review mode?"
      description="You have an active review session. Save your draft before leaving, or discard all changes."
      confirmLabel="Discard & Leave"
      variant="danger"
      extraActions={[
        {
          label: 'Save Draft & Leave',
          onClick: handleSaveAndLeave,
          variant: 'secondary',
        },
      ]}
    />
  );
}
