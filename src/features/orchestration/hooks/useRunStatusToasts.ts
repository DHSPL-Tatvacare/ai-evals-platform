import { useEffect } from 'react';

import { useRunOverlayStore } from '@/features/orchestration/store/runOverlayStore';
import { notificationService } from '@/services/notifications';

/**
 * Module-level set of run ids already toasted this browser session.
 * Prevents duplicate toasts when the run inspector overlay is re-opened
 * or when SSE replays a terminal-status snapshot for a run that already
 * fired its toast. Exposed via `_resetToastedForTest` for unit tests only.
 */
const toastedRunIds = new Set<string>();

/** Test-only helper — resets the dedup set between test cases. */
export function _resetToastedForTest(): void {
  toastedRunIds.clear();
}

/**
 * Watches `runStatus` from the SSE-driven overlay store and fires a single
 * toast on transition into a terminal state. Deduplicates across re-opens
 * and SSE replays via the module-level `toastedRunIds` set.
 *
 * "Run started" is already toasted by the submit handler. `cancelled` is
 * silent — the user triggered it explicitly.
 */
export function useRunStatusToasts(runId: string | undefined): void {
  const runStatus = useRunOverlayStore((s) => s.runStatus);
  const runError = useRunOverlayStore((s) => s.runError);

  useEffect(() => {
    if (!runId) return;
    if (runStatus !== 'completed' && runStatus !== 'failed') return;
    if (toastedRunIds.has(runId)) return;

    toastedRunIds.add(runId);
    const shortId = runId.slice(0, 8);

    if (runStatus === 'completed') {
      notificationService.success(`Run ${shortId} completed`);
    } else {
      notificationService.error(
        runError ? `Run ${shortId} failed: ${runError}` : `Run ${shortId} failed`,
      );
    }
  }, [runId, runStatus, runError]);
}
