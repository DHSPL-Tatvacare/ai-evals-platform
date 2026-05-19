import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiQueryFn } from '@/services/api/queryFn';
import { adminNotificationsApi, type SendLogListQuery, type SubscriptionListQuery } from './api';
import type {
  AdminMailSendList,
  AdminSubscriptionList,
  AdminSubscriptionRow,
  NotificationDefaultRow,
  NotificationDefaultsResponse,
} from './types';

export const adminNotificationsKeys = {
  all: ['admin', 'notifications'] as const,
  defaults: () => [...adminNotificationsKeys.all, 'defaults'] as const,
  subscriptions: (q: SubscriptionListQuery) =>
    [...adminNotificationsKeys.all, 'subscriptions', q] as const,
  sendLog: (q: SendLogListQuery) =>
    [...adminNotificationsKeys.all, 'send-log', q] as const,
};

function qs(params: Record<string, unknown> | SubscriptionListQuery | SendLogListQuery): string {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue;
    search.set(k, String(v));
  }
  const out = search.toString();
  return out ? `?${out}` : '';
}

export function useNotificationDefaults() {
  return useQuery<NotificationDefaultsResponse>({
    queryKey: adminNotificationsKeys.defaults(),
    queryFn: () =>
      apiQueryFn<NotificationDefaultsResponse>('/api/admin/notifications/defaults'),
  });
}

export function useAdminSubscriptions(query: SubscriptionListQuery) {
  return useQuery<AdminSubscriptionList>({
    queryKey: adminNotificationsKeys.subscriptions(query),
    queryFn: () =>
      apiQueryFn<AdminSubscriptionList>(
        `/api/admin/notifications/subscriptions${qs(query)}`,
      ),
  });
}

export function useAdminSendLog(query: SendLogListQuery) {
  return useQuery<AdminMailSendList>({
    queryKey: adminNotificationsKeys.sendLog(query),
    queryFn: () =>
      apiQueryFn<AdminMailSendList>(
        `/api/admin/notifications/send-log${qs(query)}`,
      ),
  });
}

export function useUpdateDefault() {
  const qc = useQueryClient();
  return useMutation<
    NotificationDefaultRow,
    Error,
    { eventType: string; isRequiredForAll: boolean; alwaysNotifyEmails: string[] }
  >({
    mutationFn: ({ eventType, isRequiredForAll, alwaysNotifyEmails }) =>
      adminNotificationsApi.updateDefault(eventType, {
        isRequiredForAll,
        alwaysNotifyEmails,
      }),
    onSuccess: (updated) => {
      qc.setQueryData<NotificationDefaultsResponse>(
        adminNotificationsKeys.defaults(),
        (prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            defaults: prev.defaults.map((d) =>
              d.eventType === updated.eventType ? { ...d, ...updated } : d,
            ),
          };
        },
      );
      // Subscription side mutates as a side effect of default changes.
      qc.invalidateQueries({ queryKey: adminNotificationsKeys.all });
    },
  });
}

export function usePatchSubscription() {
  const qc = useQueryClient();
  return useMutation<
    AdminSubscriptionRow,
    Error,
    { id: string; isActive?: boolean; isRequired?: boolean }
  >({
    mutationFn: ({ id, isActive, isRequired }) =>
      adminNotificationsApi.patchSubscription(id, { isActive, isRequired }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: adminNotificationsKeys.all });
    },
  });
}

export function useDeleteSubscription() {
  const qc = useQueryClient();
  return useMutation<void, Error, { id: string }>({
    mutationFn: ({ id }) => adminNotificationsApi.deleteSubscription(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: adminNotificationsKeys.all });
    },
  });
}
