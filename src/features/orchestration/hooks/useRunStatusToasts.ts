import { useEffect, useRef } from 'react';

import { useRunOverlayStore } from '@/features/orchestration/store/runOverlayStore';
import { notificationService } from '@/services/notifications';

/**
 * Watches `runStatus` from the SSE-driven overlay store and fires a single
 * toast on transition into a terminal state. The "Run started" toast is
 * already fired by the manual-run handler at submit time, so this hook
 * only fires for completed / failed.
 *
 * Tracks the previous status with a ref so re-renders that re-read the
 * same status don't re-fire. `cancelled` is silent because the user
 * triggered it explicitly.
 */
export function useRunStatusToasts(runId: string | undefined): void {
  const runStatus = useRunOverlayStore((s) => s.runStatus);
  const runError = useRunOverlayStore((s) => s.runError);
  const previous = useRef<typeof runStatus>('pending');

  useEffect(() => {
    if (!runId) return;
    const prev = previous.current;
    previous.current = runStatus;

    if (prev === runStatus) return;

    const shortId = runId.slice(0, 8);
    if (runStatus === 'completed') {
      notificationService.success(`Run ${shortId} completed`);
    } else if (runStatus === 'failed') {
      notificationService.error(
        runError ? `Run ${shortId} failed: ${runError}` : `Run ${shortId} failed`,
      );
    }
  }, [runId, runStatus, runError]);
}
