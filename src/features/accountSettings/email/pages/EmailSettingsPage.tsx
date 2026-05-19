import { useMemo, useState } from 'react';
import { notificationService } from '@/services/notifications';
import { decodeApiError, summarizeApiErrorBody } from '@/features/orchestration/contracts/errorDecoder';
import { LoadingState } from '@/components/ui/LoadingState';
import { emailSettingsCopy } from '../emailSettings.copy';
import {
  useEmailSettings,
  useRecentSends,
  useToggleSubscription,
  useUpdateRecipient,
} from '../queries';
import type { NotificationSubscriptionRow } from '../types';
import { RecipientAddressRow } from '../components/RecipientAddressRow';
import { ChangeRecipientOverlay } from '../components/ChangeRecipientOverlay';
import { EventGroupCard } from '../components/EventGroupCard';
import { EventToggleRow } from '../components/EventToggleRow';
import { RecentSendsTable } from '../components/RecentSendsTable';

function groupSubscriptions(
  subs: NotificationSubscriptionRow[],
): Array<{ group: string; rows: NotificationSubscriptionRow[] }> {
  const order: string[] = [];
  const byGroup = new Map<string, NotificationSubscriptionRow[]>();
  for (const row of subs) {
    if (!byGroup.has(row.group)) {
      byGroup.set(row.group, []);
      order.push(row.group);
    }
    byGroup.get(row.group)!.push(row);
  }
  return order.map((group) => ({ group, rows: byGroup.get(group)! }));
}

export function EmailSettingsPage() {
  const settingsQuery = useEmailSettings();
  const recentSends = useRecentSends();
  const toggleMutation = useToggleSubscription();
  const recipientMutation = useUpdateRecipient();
  const [overlayOpen, setOverlayOpen] = useState(false);
  const [pendingEventType, setPendingEventType] = useState<string | null>(null);

  const grouped = useMemo(() => {
    if (!settingsQuery.data) return [];
    return groupSubscriptions(settingsQuery.data.subscriptions);
  }, [settingsQuery.data]);

  const handleToggle = (row: NotificationSubscriptionRow, next: boolean) => {
    setPendingEventType(row.eventType);
    toggleMutation.mutate(
      { eventType: row.eventType, isActive: next },
      {
        onSuccess: () => {
          notificationService.success(emailSettingsCopy.toast.subscriptionUpdated);
        },
        onError: (err) => {
          const decoded = decodeApiError(err);
          notificationService.error(
            summarizeApiErrorBody(decoded, emailSettingsCopy.error.updateFailed),
          );
        },
        onSettled: () => {
          setPendingEventType(null);
        },
      },
    );
  };

  const handleRecipientSubmit = async (next: string) => {
    await recipientMutation
      .mutateAsync({ recipientEmail: next })
      .then(() => {
        notificationService.success(emailSettingsCopy.toast.recipientUpdated);
        setOverlayOpen(false);
      })
      .catch((err) => {
        const decoded = decodeApiError(err);
        notificationService.error(
          summarizeApiErrorBody(decoded, emailSettingsCopy.error.recipientFailed),
        );
        throw err;
      });
  };

  if (settingsQuery.isLoading) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-8">
        <LoadingState />
      </div>
    );
  }

  if (settingsQuery.isError || !settingsQuery.data) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-8">
        <p className="text-[13px] text-[var(--color-error)]">
          {emailSettingsCopy.error.listFailed}
        </p>
      </div>
    );
  }

  const data = settingsQuery.data;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-8">
      <header>
        <h1 className="text-[20px] font-semibold text-[var(--text-primary)]">
          {emailSettingsCopy.title}
        </h1>
        <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
          {emailSettingsCopy.subtitle}
        </p>
      </header>

      <RecipientAddressRow
        recipientEmail={data.recipientEmail}
        onChange={() => setOverlayOpen(true)}
      />

      <section>
        <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
          {emailSettingsCopy.notificationsHeader}
        </h2>
        <div className="flex flex-col gap-3">
          {grouped.map(({ group, rows }) => (
            <EventGroupCard
              key={group}
              title={emailSettingsCopy.groups[group] ?? group}
            >
              {rows.map((row) => (
                <EventToggleRow
                  key={row.eventType}
                  row={row}
                  pending={pendingEventType === row.eventType && toggleMutation.isPending}
                  onToggle={(next) => handleToggle(row, next)}
                />
              ))}
            </EventGroupCard>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-[13px] font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
          {emailSettingsCopy.recentSendsHeader}
        </h2>
        <p className="mb-3 text-[12px] text-[var(--text-tertiary)]">
          {emailSettingsCopy.recentSendsSubtitle}
        </p>
        <RecentSendsTable rows={recentSends.data ?? []} loading={recentSends.isLoading} />
        {recentSends.isError ? (
          <p className="mt-2 text-[12px] text-[var(--color-error)]">
            {emailSettingsCopy.error.recentSendsFailed}
          </p>
        ) : null}
      </section>

      {overlayOpen ? (
        <ChangeRecipientOverlay
          isOpen
          currentRecipient={data.recipientEmail}
          onClose={() => setOverlayOpen(false)}
          onSubmit={handleRecipientSubmit}
          submitting={recipientMutation.isPending}
        />
      ) : null}
    </div>
  );
}
