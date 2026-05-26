import { useMemo } from 'react';
import { useWorkflowRuns } from '@/features/orchestration/queries/runs';
import { isRunActive, type WorkflowRun } from '@/features/orchestration/types';

/** Newest active run from a newest-first list, else null. Pure — tested. */
export function pickLiveRun(runs: WorkflowRun[] | undefined): WorkflowRun | null {
  return runs?.find((r) => isRunActive(r.status)) ?? null;
}

/** Live run for a workflow, derived from the polling runs query (server
 *  truth). Survives navigation because the TQ cache + refetch is global. */
export function useLiveWorkflowRun(workflowId: string | null | undefined) {
  const runsQuery = useWorkflowRuns(workflowId);
  const liveRun = useMemo(
    () => pickLiveRun(runsQuery.data?.runs),
    [runsQuery.data?.runs],
  );
  return { liveRun, runsQuery };
}
