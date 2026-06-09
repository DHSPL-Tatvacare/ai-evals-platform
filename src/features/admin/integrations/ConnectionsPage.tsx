import { useEffect, useId, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Copy, Database, Pencil, PlugZap, Power, PowerOff, RefreshCw, X } from 'lucide-react';

import { routes } from '@/config/routes';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ConnectionProviderLogo } from '@/components/ui/ConnectionProviderLogo';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { DataTable, type ColumnDef } from '@/components/ui/DataTable';
import { PageSurface } from '@/components/ui/PageSurface';
import { RightSlideOverShell } from '@/components/ui/RightSlideOverShell';
import { RowActionsMenu, type RowAction } from '@/components/ui/RowActionsMenu';
import { usePageMetadata } from '@/config/pageMetadata';
import { ApiError } from '@/services/api/client';
import { type Connection } from '@/services/api/orchestrationConnections';
import { notificationService } from '@/services/notifications';
import { logger } from '@/services/logger';
import { useAuthStore } from '@/stores/authStore';

import { CONNECTION_PROVIDER_KINDS } from '@/constants/connectionProviders';

import { ConnectionForm } from './ConnectionForm';
import { getConnectionProviderLabel } from './providerOptions';
import {
  useConnections,
  useRotateToken,
  useTestConnection,
  useUpdateConnection,
} from './queries';
import {
  canEditOrchestrationAsset,
  canManageOrchestration,
} from '@/features/orchestration/utils/access';

// One row per connection; the Category column distinguishes comm vs data.
const COMM_KINDS = new Set(['voice', 'messaging']);

function isCommConnection(c: Connection): boolean {
  return COMM_KINDS.has(CONNECTION_PROVIDER_KINDS[c.provider] ?? 'messaging');
}

function fmtDate(s: string | null): string {
  if (!s) return '—';
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleString();
}

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (err) {
    logger.warn('clipboard write failed', { err: String(err) });
    return false;
  }
}

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

export function ConnectionsPage() {
  // Relocated to the admin sidebar. The app slug is no longer
  // taken from the URL path — tenant scoping comes from the bearer token,
  // and an optional `?app=` query param filters the list (and supplies the
  // app the create form binds new connections to).
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const appId = searchParams.get('app') ?? undefined;
  const { icon, title } = usePageMetadata('connections');
  const user = useAuthStore((s) => s.user);
  const canManage = canManageOrchestration(user);
  const createTitleId = useId();
  const editTitleId = useId();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Connection | null>(null);
  const [deactivateTarget, setDeactivateTarget] = useState<Connection | null>(null);
  // Single-open per page — opening a row's menu closes any other row's.
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);

  const connectionsQuery = useConnections({ appId, includeInactive: true });
  const testMutation = useTestConnection();
  const rotateMutation = useRotateToken();
  const updateMutation = useUpdateConnection();

  const rows = useMemo(() => connectionsQuery.data ?? [], [connectionsQuery.data]);
  const loading = connectionsQuery.isLoading;

  useEffect(() => {
    if (connectionsQuery.error) {
      notificationService.error(
        errorMessage(connectionsQuery.error, 'Failed to load connections'),
      );
    }
  }, [connectionsQuery.error]);

  function handleTest(connection: Connection) {
    testMutation.mutate(connection.id, {
      onSuccess: (result) => {
        if (result.ok) {
          notificationService.success(
            `Test passed: ${result.detail || connection.provider}`,
          );
        } else {
          notificationService.error(`Test failed: ${result.detail}`);
        }
      },
      onError: (err) => {
        notificationService.error(errorMessage(err, 'Test failed'));
      },
    });
  }

  function handleRotate(connection: Connection) {
    rotateMutation.mutate(connection.id, {
      onSuccess: async (result) => {
        notificationService.success('Webhook URL rotated. Update the provider dashboard.');
        // Best-effort: copy the new URL so the operator can paste it into
        // the provider dashboard without a second click.
        if (result.webhookUrl) await copyToClipboard(result.webhookUrl);
      },
      onError: (err) => {
        notificationService.error(errorMessage(err, 'Failed to rotate token'));
      },
    });
  }

  function setActive(connection: Connection, active: boolean) {
    updateMutation.mutate(
      { id: connection.id, body: { active } },
      {
        onSuccess: () => {
          notificationService.success(
            active
              ? `"${connection.name}" is now active`
              : `"${connection.name}" is now inactive`,
          );
          setDeactivateTarget(null);
        },
        onError: (err) => {
          notificationService.error(
            errorMessage(err, 'Failed to update connection'),
          );
        },
      },
    );
  }

  const columns: ColumnDef<Connection>[] = [
    {
      key: 'name',
      header: 'Name',
      render: (c) => (
        <span className="text-[var(--text-primary)]">{c.name}</span>
      ),
    },
    {
      key: 'provider',
      header: 'Provider',
      render: (c) => (
        <div className="flex items-center gap-2">
          <ConnectionProviderLogo provider={c.provider} size={18} />
          <Badge variant="neutral" size="sm">
            {getConnectionProviderLabel(c.provider)}
          </Badge>
        </div>
      ),
    },
    {
      key: 'category',
      header: 'Category',
      render: (c) =>
        isCommConnection(c) ? (
          <Badge variant="info" size="sm">
            Communication
          </Badge>
        ) : (
          <Badge variant="neutral" size="sm">
            Data &amp; CRM
          </Badge>
        ),
    },
    {
      key: 'active',
      header: 'Status',
      render: (c) =>
        c.active ? (
          <Badge variant="success" size="sm">
            Active
          </Badge>
        ) : (
          <Badge variant="neutral" size="sm">
            Inactive
          </Badge>
        ),
    },
    {
      key: 'lastUsedAt',
      header: 'Last Used',
      render: (c) => (
        <span className="text-[var(--text-secondary)]">
          {fmtDate(c.lastUsedAt)}
        </span>
      ),
    },
    {
      key: 'webhookUrl',
      header: 'Webhook URL',
      textBehavior: 'truncate',
      render: (c) =>
        c.webhookUrl ? (
          <button
            type="button"
            className="inline-flex max-w-[260px] items-center gap-1 truncate font-mono text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            onClick={async (e) => {
              e.stopPropagation();
              const ok = await copyToClipboard(c.webhookUrl!);
              if (ok) notificationService.success('Webhook URL copied');
            }}
            title="Click to copy"
          >
            <Copy className="h-3 w-3 shrink-0" />
            <span className="truncate">{c.webhookUrl}</span>
          </button>
        ) : (
          <span className="text-[length:var(--text-table-header)] text-[var(--text-muted)]">—</span>
        ),
    },
    {
      key: '_actions',
      header: 'Actions',
      width: 'w-[80px]',
      headerClassName: 'text-right',
      cellClassName: 'text-right',
      render: (c) => {
        const canEdit = canEditOrchestrationAsset(user, c.createdBy);
        const testing = testMutation.isPending && testMutation.variables === c.id;
        const rotating = rotateMutation.isPending && rotateMutation.variables === c.id;
        const updating =
          updateMutation.isPending && updateMutation.variables?.id === c.id;
        const actions: RowAction[] = [
          {
            id: 'test',
            icon: PlugZap,
            label: testing ? 'Testing…' : 'Test connection',
            disabled: !canEdit || testing,
            onClick: () => {
              handleTest(c);
            },
          },
          {
            id: 'edit',
            icon: Pencil,
            label: 'Edit',
            disabled: !canEdit,
            onClick: () => setEditing(c),
          },
          {
            // CRM-source connections carry a data surface (mapping + filter +
            // schedule); managing it is part of managing the connection (same
            // orchestration:manage gate). Opens the full-page data surface.
            id: 'manageData',
            icon: Database,
            label: 'Manage data',
            disabled: !canEdit,
            hidden: CONNECTION_PROVIDER_KINDS[c.provider] !== 'crm_source',
            onClick: () => navigate(routes.connectionData(c.id)),
          },
          {
            id: 'rotate',
            icon: RefreshCw,
            label: rotating ? 'Rotating…' : 'Rotate webhook URL',
            disabled: !canEdit || rotating,
            // Only relevant when the connection exposes an inbound
            // webhook (Bolna / WATI). Hidden otherwise so the menu
            // doesn't bait the operator with an irrelevant action.
            hidden: !c.webhookUrl,
            onClick: () => {
              handleRotate(c);
            },
          },
          {
            // Reversible lifecycle: deactivate halts live dispatch/webhooks
            // (confirm), activate is immediate. Both ride the PATCH active.
            id: 'toggleActive',
            icon: c.active ? PowerOff : Power,
            label: c.active ? 'Deactivate' : 'Activate',
            danger: c.active,
            disabled: !canEdit || updating,
            onClick: () => {
              if (c.active) setDeactivateTarget(c);
              else setActive(c, true);
            },
          },
        ];
        return (
          <div className="flex items-center justify-end">
            <RowActionsMenu
              actions={actions}
              open={openMenuId === c.id}
              onOpenChange={(open) => setOpenMenuId(open ? c.id : null)}
            />
          </div>
        );
      },
    },
  ];

  return (
    <>
      <PageSurface
        icon={icon}
        title={title}
        actions={
          canManage ? (
            <Button onClick={() => setCreating(true)}>New Connection</Button>
          ) : null
        }
      >
        <div className="flex min-h-0 flex-1 flex-col">
          <DataTable<Connection>
            data={rows}
            columns={columns}
            keyExtractor={(c) => c.id}
            loading={loading}
            emptyTitle="No connections yet"
            emptyDescription="Connect a provider — Bolna or WATI for campaigns, LeadSquared or another CRM to sync leads."
          />
        </div>
      </PageSurface>

      <RightSlideOverShell
        isOpen={creating}
        onClose={() => setCreating(false)}
        labelledBy={createTitleId}
      >
        <div className="shrink-0 flex items-start justify-between gap-4 px-6 py-4 border-b border-[var(--border-default)] bg-[var(--bg-secondary)]">
          <h2
            id={createTitleId}
            className="text-sm font-semibold text-[var(--text-primary)]"
          >
            New Connection
          </h2>
          <button
            onClick={() => setCreating(false)}
            className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {creating ? (
            <ConnectionForm
              appId={appId}
              onClose={() => setCreating(false)}
              onSaved={() => {
                setCreating(false);
                void connectionsQuery.refetch();
              }}
            />
          ) : null}
        </div>
      </RightSlideOverShell>

      <RightSlideOverShell
        isOpen={Boolean(editing)}
        onClose={() => setEditing(null)}
        labelledBy={editTitleId}
      >
        <div className="shrink-0 flex items-start justify-between gap-4 px-6 py-4 border-b border-[var(--border-default)] bg-[var(--bg-secondary)]">
          <div className="flex items-center gap-2 min-w-0">
            {editing ? (
              <ConnectionProviderLogo provider={editing.provider} size={24} />
            ) : null}
            <h2
              id={editTitleId}
              className="truncate text-sm font-semibold text-[var(--text-primary)]"
            >
              {editing ? `Edit ${editing.name}` : ''}
            </h2>
          </div>
          <button
            onClick={() => setEditing(null)}
            className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {editing ? (
            <ConnectionForm
              appId={editing.appId}
              existing={editing}
              onClose={() => setEditing(null)}
              onSaved={() => {
                setEditing(null);
                void connectionsQuery.refetch();
              }}
            />
          ) : null}
        </div>
      </RightSlideOverShell>

      <ConfirmDialog
        isOpen={Boolean(deactivateTarget)}
        onClose={() => setDeactivateTarget(null)}
        onConfirm={() => deactivateTarget && setActive(deactivateTarget, false)}
        title="Deactivate connection"
        description={
          deactivateTarget
            ? `Deactivate "${deactivateTarget.name}"? Live dispatch and incoming webhooks for this connection stop immediately. You can reactivate it any time.`
            : ''
        }
        confirmLabel="Deactivate"
        variant="danger"
      />
    </>
  );
}
