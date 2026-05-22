/**
 * Workflow-versioning redesign — TanStack Query hooks for the workflow
 * draft/publish lifecycle. The builder reads server data (the workflow row
 * with its single mutable `draftDefinition`, and the published version
 * history) through these hooks instead of bespoke `useEffect` fetches, per
 * the platform "server data → TQ" invariant. Mirrors `queries/runs.ts`.
 *
 * Lifecycle endpoints (new model):
 *   - SAVE    → `PUT /workflows/{id}/draft`   (overwrites the draft, no version)
 *   - PUBLISH → `POST /workflows/{id}/publish` (mints one immutable version)
 *   - LOAD    → `GET /workflows/{id}`          (carries `draftDefinition`)
 *   - HISTORY → `GET /workflows/{id}/versions` (published versions, version DESC)
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  getWorkflow,
  listVersions,
  publishDraft,
  saveDraft,
} from '@/services/api/orchestration';
import type {
  Workflow,
  WorkflowDefinition,
  WorkflowVersion,
} from '@/features/orchestration/types';

const WORKFLOW_STALE_TIME_MS = 30_000;

export const workflowQueryKeys = {
  workflow: (workflowId: string) =>
    ['orchestration', 'workflow', workflowId] as const,
  versions: (workflowId: string) =>
    ['orchestration', 'workflow', workflowId, 'versions'] as const,
};

/** The workflow row, including its single mutable `draftDefinition` and the
 *  `currentPublishedVersionId` pointer. The builder hydrates the canvas from
 *  `draftDefinition` (falling back to the live published def). */
export function useWorkflow(workflowId: string | null | undefined) {
  const enabled = Boolean(workflowId);
  return useQuery<Workflow>({
    queryKey: enabled
      ? workflowQueryKeys.workflow(workflowId as string)
      : (['orchestration', 'workflow', '__disabled__'] as const),
    queryFn: () => getWorkflow(workflowId as string),
    enabled,
    staleTime: WORKFLOW_STALE_TIME_MS,
  });
}

/** Published version history for a workflow (`version DESC`, published only).
 *  The builder reads this to resolve the live published definition for the
 *  `publishedDataHash` seed; a future PR adds the history/rollback panel. */
export function useWorkflowVersions(workflowId: string | null | undefined) {
  const enabled = Boolean(workflowId);
  return useQuery<WorkflowVersion[]>({
    queryKey: enabled
      ? workflowQueryKeys.versions(workflowId as string)
      : (['orchestration', 'workflow', '__disabled__', 'versions'] as const),
    queryFn: () => listVersions(workflowId as string),
    enabled,
    staleTime: WORKFLOW_STALE_TIME_MS,
  });
}

/** Save the current draft (`PUT /draft`). Overwrites the workflow's single
 *  mutable draft in place — never mints a version. Returns the updated
 *  workflow row (with the new `draftDefinition` / `draftUpdatedAt`). Settles
 *  the workflow cache so the row reflects the saved draft. */
export function useSaveDraftMutation() {
  const queryClient = useQueryClient();
  return useMutation<
    Workflow,
    unknown,
    { workflowId: string; definition: WorkflowDefinition }
  >({
    mutationFn: ({ workflowId, definition }) => saveDraft(workflowId, definition),
    onSuccess: (workflow, { workflowId }) => {
      queryClient.setQueryData(workflowQueryKeys.workflow(workflowId), workflow);
    },
  });
}

/** Publish the current draft (`POST /publish`, no version id). Mints one
 *  immutable version and repoints `currentPublishedVersionId`. Invalidates the
 *  workflow + version-history caches so the header pill and (future) history
 *  panel reflect the new live version without a reload. Error decoding +
 *  the `PublishErrorPanel` 400/422 handling stay with the caller. */
export function usePublishMutation() {
  const queryClient = useQueryClient();
  return useMutation<WorkflowVersion, unknown, { workflowId: string }>({
    mutationFn: ({ workflowId }) => publishDraft(workflowId),
    onSuccess: (_version, { workflowId }) => {
      void queryClient.invalidateQueries({
        queryKey: workflowQueryKeys.workflow(workflowId),
      });
      void queryClient.invalidateQueries({
        queryKey: workflowQueryKeys.versions(workflowId),
      });
    },
  });
}
