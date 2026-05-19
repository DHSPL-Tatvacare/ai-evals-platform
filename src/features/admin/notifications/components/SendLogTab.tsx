import { useState } from 'react';
import { Mail } from 'lucide-react';
import type { ColumnDef } from '@/components/ui/DataTable';
import { DataTable } from '@/components/ui/DataTable';
import { Badge, type BadgeVariant } from '@/components/ui/Badge';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { emailSettingsCopy } from '@/features/accountSettings/email/emailSettings.copy';
import { adminNotificationsCopy } from '../adminNotifications.copy';
import { useAdminSendLog } from '../queries';
import type { AdminMailSendRow } from '../types';

const PAGE_SIZE = 25;

const STATUS_VARIANT: Record<string, BadgeVariant> = {
  sent: 'success',
  failed: 'error',
  bounced: 'warning',
  not_configured: 'neutral',
};

const STATUS_OPTIONS = [
  { value: '', label: adminNotificationsCopy.sendLog.filters.allStatuses },
  { value: 'sent', label: emailSettingsCopy.status.sent },
  { value: 'failed', label: emailSettingsCopy.status.failed },
  { value: 'bounced', label: emailSettingsCopy.status.bounced },
  { value: 'not_configured', label: emailSettingsCopy.status.not_configured },
];

const CALL_SITE_OPTIONS = [
  { value: '', label: adminNotificationsCopy.sendLog.filters.allEvents },
  { value: 'mail.signup_invite', label: 'Signup invite' },
  ...Object.keys(emailSettingsCopy.events).map((eventType) => ({
    value: `mail.${eventType.replace('.', '_')}`,
    label: emailSettingsCopy.events[eventType] ?? eventType,
  })),
];

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function SendLogTab() {
  const [status, setStatus] = useState('');
  const [callSite, setCallSite] = useState('');
  const [recipient, setRecipient] = useState('');
  const [page, setPage] = useState(1);

  const query = useAdminSendLog({
    status: status || undefined,
    callSite: callSite || undefined,
    recipient: recipient || undefined,
    page,
    pageSize: PAGE_SIZE,
  });

  const columns: ColumnDef<AdminMailSendRow>[] = [
    {
      key: 'sentAt',
      header: adminNotificationsCopy.sendLog.columns.sentAt,
      width: '180px',
      render: (row) => (
        <span className="text-[12px] text-[var(--text-secondary)]">
          {formatTime(row.sentAt)}
        </span>
      ),
      textBehavior: 'nowrap',
    },
    {
      key: 'recipient',
      header: adminNotificationsCopy.sendLog.columns.recipient,
      width: '220px',
      render: (row) => (
        <span className="text-[13px] text-[var(--text-primary)]" title={row.recipient}>
          {row.recipient}
        </span>
      ),
      textBehavior: 'truncate',
    },
    {
      key: 'subject',
      header: adminNotificationsCopy.sendLog.columns.subject,
      render: (row) => (
        <span className="text-[13px] text-[var(--text-primary)]" title={row.subject}>
          {row.subject}
        </span>
      ),
      textBehavior: 'truncate',
    },
    {
      key: 'status',
      header: adminNotificationsCopy.sendLog.columns.status,
      width: '160px',
      render: (row) => (
        <Badge variant={STATUS_VARIANT[row.status] ?? 'neutral'}>
          {emailSettingsCopy.status[row.status] ?? row.status}
        </Badge>
      ),
      textBehavior: 'nowrap',
    },
  ];

  const totalPages = Math.max(1, Math.ceil((query.data?.total ?? 0) / PAGE_SIZE));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1 text-[12px] text-[var(--text-secondary)]">
          <span className="font-medium">{adminNotificationsCopy.sendLog.filters.status}</span>
          <Select
            size="sm"
            value={status}
            onChange={(v) => {
              setStatus(v);
              setPage(1);
            }}
            options={STATUS_OPTIONS}
          />
        </div>
        <div className="flex flex-col gap-1 text-[12px] text-[var(--text-secondary)]">
          <span className="font-medium">{adminNotificationsCopy.sendLog.filters.event}</span>
          <Select
            size="sm"
            value={callSite}
            onChange={(v) => {
              setCallSite(v);
              setPage(1);
            }}
            options={CALL_SITE_OPTIONS}
          />
        </div>
        <div className="flex flex-col gap-1 text-[12px] text-[var(--text-secondary)]">
          <span className="font-medium">{adminNotificationsCopy.sendLog.filters.recipient}</span>
          <Input
            value={recipient}
            onChange={(e) => {
              setRecipient(e.target.value);
              setPage(1);
            }}
            placeholder="alice@…"
            className="h-8 w-[220px]"
          />
        </div>
      </div>

      {query.isError ? (
        <p className="text-[13px] text-[var(--color-error)]">
          {adminNotificationsCopy.sendLog.loadFailed}
        </p>
      ) : (
        <DataTable<AdminMailSendRow>
          columns={columns}
          data={query.data?.rows ?? []}
          keyExtractor={(row) => row.id}
          loading={query.isLoading}
          emptyIcon={Mail}
          emptyTitle={adminNotificationsCopy.sendLog.empty}
          pagination={{
            page,
            totalPages,
            totalItems: query.data?.total,
            onPageChange: setPage,
            pageSize: PAGE_SIZE,
            showCount: true,
          }}
        />
      )}

    </div>
  );
}
