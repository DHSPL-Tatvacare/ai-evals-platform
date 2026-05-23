import { apiRequest } from './client';
import type { WorkflowType } from '@/features/orchestration/types';

/** Event-source vendor selected on an event trigger. `webhook` is the
 *  identity passthrough (payload already canonical); the others map native
 *  CRM/clinical payloads → canonical via a per-vendor adapter. Mirrors the
 *  backend `EventSourceAdapter` registry. */
export type EventTriggerVendor = 'webhook' | 'frappe' | 'lsq' | 'mytatva';

/** Catalog response — canonical event names gated by `workflow_type`
 *  (lowercase `crm` / `clinical`) on the backend. Names are plain strings. */
export interface EventCatalogResponse {
  workflowType: WorkflowType;
  events: string[];
}

/** An event-mode trigger binding. The raw token is masked on reads
 *  (`webhookTokenMasked`); the usable inbound URL carries the token and is
 *  composed by the backend (`webhookUrl`). Mirrors `TriggerResponse`. */
export interface EventTrigger {
  id: string;
  workflowId: string;
  kind: string;
  eventName: string | null;
  vendor: EventTriggerVendor;
  /** Masked preview (e.g. `wXyZ••••AbCd`); never the live secret. */
  webhookTokenMasked: string | null;
  /** Inbound URL (absolute) the external system POSTs to. Carries the token. */
  webhookUrl: string | null;
  active: boolean;
  createdAt: string;
  updatedAt: string;
}

/** Rotate response — the refreshed inbound URL (with the new token) plus the
 *  masked preview. Mirrors the backend `TriggerRotateTokenResponse`. */
export interface RotateTokenResponse {
  webhookUrl: string | null;
  webhookTokenMasked: string;
}

export interface CreateEventTriggerBody {
  eventName: string;
  vendor: EventTriggerVendor;
  active?: boolean;
}

/** PATCH only toggles `active` — event_name/vendor are immutable post-create. */
export interface UpdateEventTriggerBody {
  active?: boolean;
}

function toAbsoluteUrl(url: string | null): string | null {
  if (!url) return null;
  if (/^https?:\/\//i.test(url)) return url;
  if (typeof window === 'undefined') return url;
  return new URL(url, window.location.origin).toString();
}

function normalizeTrigger<T extends { webhookUrl: string | null }>(trigger: T): T {
  return { ...trigger, webhookUrl: toAbsoluteUrl(trigger.webhookUrl) };
}

/** Canonical event names for the combobox, gated by the workflow's
 *  `workflow_type` (lowercase `crm` / `clinical`). Keying on the wrong case
 *  silently returns an empty list — pass the literal store value. */
export async function getEventCatalog(params: {
  workflowType: WorkflowType;
}): Promise<EventCatalogResponse> {
  const q = new URLSearchParams({ workflowType: params.workflowType });
  return apiRequest<EventCatalogResponse>(
    `/api/orchestration/event-catalog?${q.toString()}`,
  );
}

export async function listEventTriggers(workflowId: string): Promise<EventTrigger[]> {
  const rows = await apiRequest<EventTrigger[]>(
    `/api/orchestration/workflows/${workflowId}/triggers`,
  );
  return rows.filter((t) => t.kind === 'event').map(normalizeTrigger);
}

export async function createEventTrigger(
  workflowId: string,
  body: CreateEventTriggerBody,
): Promise<EventTrigger> {
  return normalizeTrigger(
    await apiRequest<EventTrigger>(
      `/api/orchestration/workflows/${workflowId}/triggers`,
      { method: 'POST', body: JSON.stringify({ kind: 'event', ...body }) },
    ),
  );
}

export async function updateEventTrigger(
  triggerId: string,
  body: UpdateEventTriggerBody,
): Promise<EventTrigger> {
  return normalizeTrigger(
    await apiRequest<EventTrigger>(`/api/orchestration/triggers/${triggerId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  );
}

export async function deleteEventTrigger(triggerId: string): Promise<void> {
  await apiRequest<void>(`/api/orchestration/triggers/${triggerId}`, {
    method: 'DELETE',
  });
}

export async function rotateEventTriggerToken(
  triggerId: string,
): Promise<RotateTokenResponse> {
  const res = await apiRequest<RotateTokenResponse>(
    `/api/orchestration/triggers/${triggerId}/rotate-token`,
    { method: 'POST' },
  );
  return { ...res, webhookUrl: toAbsoluteUrl(res.webhookUrl) };
}
