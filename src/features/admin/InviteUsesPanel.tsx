import { useEffect, useId, useState } from 'react';
import { Users, X } from 'lucide-react';
import {
  Badge,
  DataTable,
  EmptyState,
  LoadingState,
  type ColumnDef,
} from '@/components/ui';
import { adminApi } from '@/services/api/adminApi';
import type { InviteLink, InviteLinkUse } from '@/services/api/adminApi';
import { notificationService } from '@/services/notifications';
import { useRightOverlay } from '@/hooks';

function formatAbsolute(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, {
    month: 'short',
    day: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

interface InviteUsesPanelProps {
  invite: InviteLink | null;
  onClose: () => void;
}

/**
 * Right-side slide-over listing every redemption of a single invite link.
 *
 * Reuses the inline slide-over pattern from `InviteLinksSection`'s create
 * form (no shared `<SlideOver>` component exists in-tree). Permission
 * gating happens at the DataTable cell that opens this panel — the count
 * is only clickable inside `<PermissionGate action="invite_link:manage">`.
 */
export function InviteUsesPanel({ invite, onClose }: InviteUsesPanelProps) {
  const titleId = useId();
  const ariaProps = useRightOverlay(invite !== null, {
    onClose,
    labelledBy: titleId,
  });

  // ``uses`` is keyed by invite id so a stale fetch from a previous invite
  // can never resolve into the current panel — derived comparison instead
  // of a synchronous reset inside the effect.
  const [usesState, setUsesState] = useState<{ inviteId: string; rows: InviteLinkUse[] } | null>(null);
  const uses: InviteLinkUse[] | null =
    invite && usesState && usesState.inviteId === invite.id ? usesState.rows : null;

  useEffect(() => {
    if (!invite) return;
    let cancelled = false;
    const inviteId = invite.id;
    adminApi
      .listInviteUses(inviteId)
      .then((data) => {
        if (!cancelled) setUsesState({ inviteId, rows: data });
      })
      .catch(() => {
        if (!cancelled) {
          notificationService.error('Failed to load redemptions');
          setUsesState({ inviteId, rows: [] });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [invite]);

  if (!invite) return null;

  const columns: ColumnDef<InviteLinkUse>[] = [
    {
      key: 'user',
      header: 'User',
      width: 'min-w-[220px]',
      render: (u) => (
        <div className="flex flex-col">
          <span className="text-[13px] text-[var(--text-primary)]">{u.userEmail}</span>
          {!u.userId && (
            <span className="text-[11px] italic text-[var(--text-muted)]">
              account deleted
            </span>
          )}
        </div>
      ),
    },
    {
      key: 'usedAt',
      header: 'Redeemed at',
      width: 'w-[200px]',
      render: (u) => (
        <span className="tabular-nums text-[var(--text-muted)]">{formatAbsolute(u.usedAt)}</span>
      ),
    },
    {
      key: 'ipHashPrefix',
      header: 'IP signature',
      width: 'w-[160px]',
      render: (u) =>
        u.ipHashPrefix ? (
          <Badge variant="neutral" size="sm">
            <span className="font-mono text-[11px]">{u.ipHashPrefix}</span>
          </Badge>
        ) : (
          <span className="text-[var(--text-muted)]">—</span>
        ),
    },
  ];

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-[var(--bg-overlay)]" onClick={onClose} />
      <div
        {...ariaProps}
        className="relative w-full max-w-xl bg-[var(--bg-primary)] shadow-xl flex flex-col animate-in slide-in-from-right duration-200"
      >
        <div className="flex items-center justify-between border-b border-[var(--border-default)] px-5 py-4">
          <div className="flex flex-col">
            <h2 id={titleId} className="text-base font-semibold text-[var(--text-primary)]">
              Redemptions
            </h2>
            <span className="text-[12px] text-[var(--text-muted)]">
              {invite.label || 'No label'} · {invite.usesCount}
              {invite.maxUses !== null ? ` / ${invite.maxUses}` : ''} used
            </span>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-[var(--text-muted)] hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)] transition-colors"
            aria-label="Close redemptions panel"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {uses === null ? (
            <LoadingState />
          ) : uses.length === 0 ? (
            <EmptyState
              icon={Users}
              title="No redemptions yet"
              description="No one has signed up with this invite link yet."
              compact
            />
          ) : (
            <DataTable
              columns={columns}
              data={uses}
              keyExtractor={(u) => u.id}
            />
          )}
        </div>
      </div>
    </div>
  );
}
