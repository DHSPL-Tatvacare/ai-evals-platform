import { Tabs } from '@/components/ui/Tabs';
import { adminNotificationsCopy } from '../adminNotifications.copy';
import { DefaultsTab } from '../components/DefaultsTab';
import { SubscribersTab } from '../components/SubscribersTab';
import { SendLogTab } from '../components/SendLogTab';

export function AdminNotificationsPage() {
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-8">
      <header>
        <h1 className="text-[20px] font-semibold text-[var(--text-primary)]">
          {adminNotificationsCopy.adminTitle}
        </h1>
        <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
          {adminNotificationsCopy.adminSubtitle}
        </p>
      </header>

      <Tabs
        tabs={[
          {
            id: 'defaults',
            label: adminNotificationsCopy.tab.defaults,
            content: <DefaultsTab />,
          },
          {
            id: 'subscribers',
            label: adminNotificationsCopy.tab.subscribers,
            content: <SubscribersTab />,
          },
          {
            id: 'sendLog',
            label: adminNotificationsCopy.tab.sendLog,
            content: <SendLogTab />,
          },
        ]}
        defaultTab="defaults"
        mountStrategy="active-only"
      />
    </div>
  );
}
