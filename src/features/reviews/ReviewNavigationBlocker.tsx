import { useEffect, useCallback, useMemo } from 'react';
import { useBlocker } from 'react-router-dom';
import { ConfirmDialog } from '@/components/ui';
import { useReviewModeStore } from '@/stores/reviewModeStore';

function isAllowedPath(pathname: string, runId: string | null, threadIds: Set<string>): boolean {
  if (runId && pathname.includes(`/runs/${runId}`)) return true;
  // Only allow thread detail for threads belonging to the active run
  const threadMatch = pathname.match(/\/threads\/([^/]+)/);
  if (threadMatch && threadIds.has(threadMatch[1])) return true;
  return false;
}

export function ReviewNavigationBlocker() {
  const active = useReviewModeStore((s) => s.active);
  const runId = useReviewModeStore((s) => s.runId);
  const context = useReviewModeStore((s) => s.context);
  const saveDraft = useReviewModeStore((s) => s.saveDraft);
  const discardDraft = useReviewModeStore((s) => s.discardDraft);

  // Build set of thread IDs belonging to the active run
  const threadIds = useMemo(() => {
    if (!context?.items) return new Set<string>();
    return new Set(context.items.map((item) => {
      const raw = item.itemKey.includes(':') ? item.itemKey.split(':').slice(1).join(':') : item.itemKey;
      return raw;
    }));
  }, [context?.items]);

  const blocker = useBlocker(({ nextLocation }) => {
    if (!active) return false;
    return !isAllowedPath(nextLocation.pathname, runId, threadIds);
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
