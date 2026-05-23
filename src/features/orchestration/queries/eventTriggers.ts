/**
 * TanStack Query hooks for the event-trigger backbone (catalog + per-trigger
 * CRUD + token rotation). Server data routes through these hooks per the
 * platform "server data → TQ" invariant; the inspector never owns trigger
 * rows in component state.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  createEventTrigger,
  deleteEventTrigger,
  getEventCatalog,
  listEventTriggers,
  rotateEventTriggerToken,
  updateEventTrigger,
  type CreateEventTriggerBody,
  type EventCatalogResponse,
  type EventTrigger,
  type RotateTokenResponse,
  type UpdateEventTriggerBody,
} from '@/services/api/orchestrationTriggers';
import type { WorkflowType } from '@/features/orchestration/types';

const CATALOG_STALE_TIME_MS = 10 * 60_000;

export const eventTriggerQueryKeys = {
  catalog: (workflowType: WorkflowType, appId: string) =>
    ['orchestration', 'event-catalog', workflowType, appId] as const,
  triggers: (workflowId: string) =>
    ['orchestration', 'workflow', workflowId, 'event-triggers'] as const,
};

/** Canonical event-name catalog gated by `workflowType` (lowercase). Disabled
 *  until both the type and app id are known so a half-loaded builder never
 *  fires a bad request. */
export function useEventCatalog(
  workflowType: WorkflowType | null | undefined,
  appId: string | null | undefined,
) {
  const enabled = Boolean(workflowType) && Boolean(appId);
  return useQuery<EventCatalogResponse>({
    queryKey: enabled
      ? eventTriggerQueryKeys.catalog(workflowType as WorkflowType, appId as string)
      : (['orchestration', 'event-catalog', '__disabled__'] as const),
    queryFn: () =>
      getEventCatalog({ workflowType: workflowType as WorkflowType }),
    enabled,
    staleTime: CATALOG_STALE_TIME_MS,
  });
}

/** All event-mode trigger bindings on a workflow. The inspector manages a
 *  list — multiple triggers per workflow are expected. */
export function useEventTriggers(workflowId: string | null | undefined) {
  const enabled = Boolean(workflowId);
  return useQuery<EventTrigger[]>({
    queryKey: enabled
      ? eventTriggerQueryKeys.triggers(workflowId as string)
      : (['orchestration', 'workflow', '__disabled__', 'event-triggers'] as const),
    queryFn: () => listEventTriggers(workflowId as string),
    enabled,
  });
}

export function useCreateEventTriggerMutation(workflowId: string | null | undefined) {
  const queryClient = useQueryClient();
  return useMutation<EventTrigger, unknown, CreateEventTriggerBody>({
    mutationFn: (body) => createEventTrigger(workflowId as string, body),
    onSuccess: () => {
      if (!workflowId) return;
      void queryClient.invalidateQueries({
        queryKey: eventTriggerQueryKeys.triggers(workflowId),
      });
    },
  });
}

export function useUpdateEventTriggerMutation(workflowId: string | null | undefined) {
  const queryClient = useQueryClient();
  return useMutation<
    EventTrigger,
    unknown,
    { triggerId: string; body: UpdateEventTriggerBody }
  >({
    mutationFn: ({ triggerId, body }) => updateEventTrigger(triggerId, body),
    onSuccess: () => {
      if (!workflowId) return;
      void queryClient.invalidateQueries({
        queryKey: eventTriggerQueryKeys.triggers(workflowId),
      });
    },
  });
}

export function useDeleteEventTriggerMutation(workflowId: string | null | undefined) {
  const queryClient = useQueryClient();
  return useMutation<void, unknown, { triggerId: string }>({
    mutationFn: ({ triggerId }) => deleteEventTrigger(triggerId),
    onSuccess: () => {
      if (!workflowId) return;
      void queryClient.invalidateQueries({
        queryKey: eventTriggerQueryKeys.triggers(workflowId),
      });
    },
  });
}

export function useRotateEventTriggerTokenMutation(
  workflowId: string | null | undefined,
) {
  const queryClient = useQueryClient();
  return useMutation<RotateTokenResponse, unknown, { triggerId: string }>({
    mutationFn: ({ triggerId }) => rotateEventTriggerToken(triggerId),
    onSuccess: () => {
      if (!workflowId) return;
      void queryClient.invalidateQueries({
        queryKey: eventTriggerQueryKeys.triggers(workflowId),
      });
    },
  });
}
