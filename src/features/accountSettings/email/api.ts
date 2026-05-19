import { apiRequest } from '@/services/api/client';
import type {
  EmailSettingsPayload,
  NotificationSubscriptionRow,
  RecentSendRow,
} from './types';

const BASE = '/api/notification-subscriptions';

export const emailSettingsApi = {
  list: () => apiRequest<EmailSettingsPayload>(BASE),

  setSubscriptionActive: (eventType: string, isActive: boolean) =>
    apiRequest<NotificationSubscriptionRow>(
      `${BASE}/${encodeURIComponent(eventType)}`,
      {
        method: 'PUT',
        body: JSON.stringify({ isActive }),
      },
    ),

  setRecipient: (recipientEmail: string) =>
    apiRequest<EmailSettingsPayload>(`${BASE}/recipient`, {
      method: 'PUT',
      body: JSON.stringify({ recipientEmail }),
    }),

  recentSends: (limit = 50) =>
    apiRequest<RecentSendRow[]>(`${BASE}/recent-sends?limit=${limit}`),
};
