import { apiRequest } from './client';
import type { WorkflowType } from '@/features/orchestration/types';

/** Event-source vendor selected on an event trigger. `webhook` is the
 *  identity passthrough (payload already canonical); the others map native
 *  CRM/clinical payloads → canonical via a per-vendor adapter (T2). Mirrors
 *  the backend `EventSourceAdapter` registry. */
export type EventTriggerVendor = 'webhook' | 'frappe' | 'lsq' | 'mytatva';

/** One canonical event name plus its human label for the catalog combobox.
 *  Names are namespaced (`crm.*` / `clinical.*`) and gated by the workflow's
 *  `workflow_type` on the backend. */
export interface EventCatalogEntry {
  name: string;
  label: string;
}

export interface EventCatalogResponse {
  workflowType: WorkflowType;
  events: EventCatalogEntry[];
}

/** An event-mode trigger binding. The token is masked on GET (mirrors the
 *  `ProviderConnection` secret-strip lens) and returned in full ONCE on
 *  create / rotate. `webhookUrl`, `samplePayload`, and `curlSnippet` are
 *  composed by the backend so the "Connect your system" panel never
 *  hand-assembles the inbound contract. */
export interface EventTrigger {
  id: string;
  workflowId: string;
  kind: 'event';
  eventName: string | null;
  vendor: EventTriggerVendor;
  /** Masked preview on GET (e.g. `wXyZ••••AbCd`); never the live secret. */
  webhookTokenMasked: string | null;
  /** Origin-relative or absolute inbound URL composed by the backend. */
  webhookUrl: string | null;
  /** Verbatim sample event body for this vendor + event. */
  samplePayload: Record<string, unknown> | null;
  /** Ready-to-run curl invocation (URL + headers + sample body). */
  curlSnippet: string | null;
  active: boolean;
  createdAt: string;
  updatedAt: string;
}

/** Create / rotate responses reveal the plaintext token ONCE — the only time
 *  the UI ever sees it. The masked field is dropped to make "show once" a
 *  type-level guarantee. */
export interface EventTriggerSecretReveal extends Omit<EventTrigger, 'webhookTokenMasked'> {
  /** Plaintext token, shown exactly once. Never returned again on GET. */
  webhookToken: string;
}

export interface CreateEventTriggerBody {
  eventName: string;
  vendor: EventTriggerVendor;
  active?: boolean;
}

export interface UpdateEventTriggerBody {
  eventName?: string;
  vendor?: EventTriggerVendor;
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
  appId: string;
}): Promise<EventCatalogResponse> {
  const q = new URLSearchParams({
    workflowType: params.workflowType,
    appId: params.appId,
  });
  return apiRequest<EventCatalogResponse>(
    `/api/orchestration/event-catalog?${q.toString()}`,
  );
}

export async function listEventTriggers(workflowId: string): Promise<EventTrigger[]> {
  const rows = await apiRequest<EventTrigger[]>(
    `/api/orchestration/workflows/${workflowId}/triggers?kind=event`,
  );
  return rows.map(normalizeTrigger);
}

export async function createEventTrigger(
  workflowId: string,
  body: CreateEventTriggerBody,
): Promise<EventTriggerSecretReveal> {
  return normalizeTrigger(
    await apiRequest<EventTriggerSecretReveal>(
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
): Promise<EventTriggerSecretReveal> {
  return normalizeTrigger(
    await apiRequest<EventTriggerSecretReveal>(
      `/api/orchestration/triggers/${triggerId}/rotate-token`,
      { method: 'POST' },
    ),
  );
}
