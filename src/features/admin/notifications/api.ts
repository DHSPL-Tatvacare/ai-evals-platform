import { apiRequest } from '@/services/api/client';
import type {
  AdminMailSendList,
  AdminSubscriptionList,
  AdminSubscriptionRow,
  NotificationDefaultRow,
  NotificationDefaultsResponse,
} from './types';

const BASE = '/api/admin/notifications';

export interface SubscriptionListQuery {
  eventType?: string;
  userId?: string;
  isActive?: boolean;
  page?: number;
  pageSize?: number;
}

export interface SendLogListQuery {
  status?: string;
  callSite?: string;
  recipient?: string;
  page?: number;
  pageSize?: number;
}

function buildQuery(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : '';
}

export const adminNotificationsApi = {
  listDefaults: () => apiRequest<NotificationDefaultsResponse>(`${BASE}/defaults`),

  updateDefault: (
    eventType: string,
    body: { isRequiredForAll: boolean; alwaysNotifyEmails: string[] },
  ) =>
    apiRequest<NotificationDefaultRow>(
      `${BASE}/defaults/${encodeURIComponent(eventType)}`,
      { method: 'PUT', body: JSON.stringify(body) },
    ),

  listSubscriptions: (query: SubscriptionListQuery = {}) =>
    apiRequest<AdminSubscriptionList>(
      `${BASE}/subscriptions${buildQuery({
        eventType: query.eventType,
        userId: query.userId,
        isActive: query.isActive,
        page: query.page,
        pageSize: query.pageSize,
      })}`,
    ),

  patchSubscription: (
    id: string,
    body: { isActive?: boolean; isRequired?: boolean },
  ) =>
    apiRequest<AdminSubscriptionRow>(
      `${BASE}/subscriptions/${encodeURIComponent(id)}`,
      { method: 'PATCH', body: JSON.stringify(body) },
    ),

  deleteSubscription: (id: string) =>
    apiRequest<void>(`${BASE}/subscriptions/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    }),

  listSendLog: (query: SendLogListQuery = {}) =>
    apiRequest<AdminMailSendList>(
      `${BASE}/send-log${buildQuery({
        status: query.status,
        callSite: query.callSite,
        recipient: query.recipient,
        page: query.page,
        pageSize: query.pageSize,
      })}`,
    ),
};
