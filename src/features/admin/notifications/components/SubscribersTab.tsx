import { useState } from 'react';
import { Trash2, Lock, Users as UsersIcon } from 'lucide-react';
import type { ColumnDef } from '@/components/ui/DataTable';
import { DataTable } from '@/components/ui/DataTable';
import { Pagination } from '@/components/ui/Pagination';
import { Switch } from '@/components/ui/Switch';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Select } from '@/components/ui/Select';
import { notificationService } from '@/services/notifications';
import { decodeApiError, summarizeApiErrorBody } from '@/features/orchestration/contracts/errorDecoder';
import { emailSettingsCopy } from '@/features/accountSettings/email/emailSettings.copy';
import { adminNotificationsCopy } from '../adminNotifications.copy';
import {
  useAdminSubscriptions,
  useDeleteSubscription,
  usePatchSubscription,
} from '../queries';
import type { AdminSubscriptionRow } from '../types';

const PAGE_SIZE = 25;

const EVENT_FILTER_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: adminNotificationsCopy.subscribers.filters.allEvents },
  ...Object.keys(emailSettingsCopy.events).map((eventType) => ({
    value: eventType,
    label: emailSettingsCopy.events[eventType] ?? eventType,
  })),
];

const ACTIVE_FILTER_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: adminNotificationsCopy.subscribers.filters.allStatuses },
  { value: 'true', label: adminNotificationsCopy.subscribers.filters.activeYes },
  { value: 'false', label: adminNotificationsCopy.subscribers.filters.activeNo },
];

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function SubscribersTab() {
  const [eventFilter, setEventFilter] = useState('');
  const [activeFilter, setActiveFilter] = useState('');
  const [page, setPage] = useState(1);
  const [pendingDelete, setPendingDelete] = useState<AdminSubscriptionRow | null>(null);

  const isActive =
    activeFilter === 'true' ? true : activeFilter === 'false' ? false : undefined;
  const query = useAdminSubscriptions({
    eventType: eventFilter || undefined,
    isActive,
    page,
    pageSize: PAGE_SIZE,
  });
  const patchMutation = usePatchSubscription();
  const deleteMutation = useDeleteSubscription();

  const columns: ColumnDef<AdminSubscriptionRow>[] = [
    {
      key: 'user',
      header: adminNotificationsCopy.subscribers.columns.user,
      width: '220px',
      render: (row) => (
        <span className="text-[13px] text-[var(--text-primary)]">
          {row.userEmail ?? row.recipientEmail}
        </span>
      ),
      textBehavior: 'truncate',
    },
    {
      key: 'event',
      header: adminNotificationsCopy.subscribers.columns.event,
      render: (row) => (
        <span className="text-[13px] text-[var(--text-primary)]">
          {emailSettingsCopy.events[row.eventType] ?? row.eventType}
        </span>
      ),
      textBehavior: 'truncate',
    },
    {
      key: 'active',
      header: adminNotificationsCopy.subscribers.columns.active,
      width: '90px',
      render: (row) => (
        <Switch
          size="sm"
          checked={row.isActive}
          disabled={patchMutation.isPending && patchMutation.variables?.id === row.id}
          onCheckedChange={(next) =>
            patchMutation.mutate(
              { id: row.id, isActive: next },
              {
                onSuccess: () =>
                  notificationService.success(adminNotificationsCopy.toast.subscriptionUpdated),
                onError: (err) =>
                  notificationService.error(
                    summarizeApiErrorBody(
                      decodeApiError(err),
                      adminNotificationsCopy.subscribers.updateFailed,
                    ),
                  ),
              },
            )
          }
        />
      ),
    },
    {
      key: 'required',
      header: adminNotificationsCopy.subscribers.columns.required,
      width: '120px',
      render: (row) =>
        row.isRequired ? (
          <Badge variant="primary" icon={Lock}>
            Required
          </Badge>
        ) : (
          <span className="text-[12px] text-[var(--text-tertiary)]">—</span>
        ),
    },
    {
      key: 'created',
      header: adminNotificationsCopy.subscribers.columns.created,
      width: '170px',
      render: (row) => (
        <span className="text-[12px] text-[var(--text-secondary)]">
          {formatTime(row.createdAt)}
        </span>
      ),
      textBehavior: 'nowrap',
    },
    {
      key: 'actions',
      header: '',
      width: '60px',
      render: (row) => (
        <Button
          size="sm"
          variant="ghost"
          iconOnly
          icon={Trash2}
          aria-label={adminNotificationsCopy.subscribers.action.delete}
          onClick={() => setPendingDelete(row)}
        />
      ),
    },
  ];

  const totalPages = Math.max(1, Math.ceil((query.data?.total ?? 0) / PAGE_SIZE));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <FilterSelect
          label={adminNotificationsCopy.subscribers.filters.event}
          value={eventFilter}
          options={EVENT_FILTER_OPTIONS}
          onChange={(v) => {
            setEventFilter(v);
            setPage(1);
          }}
        />
        <FilterSelect
          label={adminNotificationsCopy.subscribers.filters.active}
          value={activeFilter}
          options={ACTIVE_FILTER_OPTIONS}
          onChange={(v) => {
            setActiveFilter(v);
            setPage(1);
          }}
        />
      </div>

      {query.isError ? (
        <p className="text-[13px] text-[var(--color-error)]">
          {adminNotificationsCopy.subscribers.loadFailed}
        </p>
      ) : (
        <DataTable<AdminSubscriptionRow>
          columns={columns}
          data={query.data?.rows ?? []}
          keyExtractor={(row) => row.id}
          loading={query.isLoading}
          emptyIcon={UsersIcon}
          emptyTitle={adminNotificationsCopy.subscribers.empty}
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

      <ConfirmDialog
        isOpen={pendingDelete !== null}
        title={adminNotificationsCopy.subscribers.action.delete}
        description={adminNotificationsCopy.subscribers.confirmDelete}
        confirmLabel={adminNotificationsCopy.subscribers.action.delete}
        cancelLabel="Cancel"
        variant="danger"
        onClose={() => setPendingDelete(null)}
        onConfirm={() => {
          if (!pendingDelete) return;
          const row = pendingDelete;
          deleteMutation.mutate(
            { id: row.id },
            {
              onSuccess: () => {
                notificationService.success(adminNotificationsCopy.toast.subscriptionRemoved);
                setPendingDelete(null);
              },
              onError: (err) => {
                notificationService.error(
                  summarizeApiErrorBody(
                    decodeApiError(err),
                    adminNotificationsCopy.subscribers.removeFailed,
                  ),
                );
              },
            },
          );
        }}
        isLoading={deleteMutation.isPending}
      />

      <Pagination
        page={page}
        totalPages={totalPages}
        onPageChange={setPage}
      />
    </div>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (next: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1 text-[12px] text-[var(--text-secondary)]">
      <span className="font-medium">{label}</span>
      <Select size="sm" value={value} onChange={onChange} options={options} />
    </div>
  );
}
