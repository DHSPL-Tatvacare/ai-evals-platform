import { useCallback, useEffect, useState } from 'react';
import { Copy, RefreshCw } from 'lucide-react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { DataTable, type ColumnDef } from '@/components/ui/DataTable';
import { Modal } from '@/components/ui/Modal';
import { PageSurface } from '@/components/ui/PageSurface';
import { usePageMetadata } from '@/config/pageMetadata';
import { ApiError } from '@/services/api/client';
import {
  archiveConnection,
  listConnections,
  rotateWebhookToken,
  testConnection,
  type Connection,
} from '@/services/api/orchestrationConnections';
import { notificationService } from '@/services/notifications';
import { logger } from '@/services/logger';

import { ConnectionForm } from './ConnectionForm';

const APP_ID = 'inside-sales';

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

export function ConnectionsPage() {
  const { icon, title } = usePageMetadata('connections');
  const [rows, setRows] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Connection | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<Connection | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [rotatingId, setRotatingId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const result = await listConnections({
        appId: APP_ID,
        includeInactive: true,
      });
      setRows(result);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : 'Failed to load connections';
      notificationService.error(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handleTest(connection: Connection) {
    setTestingId(connection.id);
    try {
      const result = await testConnection(connection.id);
      if (result.ok) {
        notificationService.success(
          `Test passed: ${result.detail || connection.provider}`,
        );
      } else {
        notificationService.error(`Test failed: ${result.detail}`);
      }
    } catch (err) {
      notificationService.error(
        err instanceof Error ? err.message : 'Test failed',
      );
    } finally {
      setTestingId(null);
    }
  }

  async function handleRotate(connection: Connection) {
    setRotatingId(connection.id);
    try {
      const result = await rotateWebhookToken(connection.id);
      notificationService.success('Webhook URL rotated. Update the provider dashboard.');
      await refresh();
      // Best-effort: also copy the new URL to clipboard so the operator can
      // paste it into the provider dashboard without a second click.
      if (result.webhookUrl) await copyToClipboard(result.webhookUrl);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : 'Failed to rotate token';
      notificationService.error(msg);
    } finally {
      setRotatingId(null);
    }
  }

  async function handleArchive() {
    if (!archiveTarget) return;
    try {
      await archiveConnection(archiveTarget.id);
      notificationService.success(`Archived "${archiveTarget.name}"`);
      setArchiveTarget(null);
      await refresh();
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : 'Failed to archive';
      notificationService.error(msg);
    }
  }

  const columns: ColumnDef<Connection>[] = [
    {
      key: 'name',
      header: 'Name',
      render: (c) => (
        <div className="flex flex-col gap-0.5">
          <span className="text-[var(--text-primary)]">{c.name}</span>
          {!c.active ? (
            <span className="text-[11px] text-[var(--text-secondary)]">Archived</span>
          ) : null}
        </div>
      ),
    },
    {
      key: 'provider',
      header: 'Provider',
      render: (c) => (
        <Badge variant="neutral" size="sm">
          {c.provider}
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
          <span className="text-[11px] text-[var(--text-muted)]">—</span>
        ),
    },
    {
      key: '_actions',
      header: '',
      width: '320px',
      render: (c) => (
        <div className="flex items-center justify-end gap-1">
          <Button
            size="sm"
            variant="secondary"
            onClick={(e) => {
              e.stopPropagation();
              void handleTest(c);
            }}
            disabled={testingId === c.id}
          >
            {testingId === c.id ? 'Testing…' : 'Test'}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={(e) => {
              e.stopPropagation();
              setEditing(c);
            }}
          >
            Edit
          </Button>
          {c.webhookUrl ? (
            <Button
              size="sm"
              variant="secondary"
              onClick={(e) => {
                e.stopPropagation();
                void handleRotate(c);
              }}
              disabled={rotatingId === c.id}
              icon={RefreshCw}
            >
              {rotatingId === c.id ? 'Rotating…' : 'Rotate'}
            </Button>
          ) : null}
          {c.active ? (
            <Button
              size="sm"
              variant="danger-outline"
              onClick={(e) => {
                e.stopPropagation();
                setArchiveTarget(c);
              }}
            >
              Archive
            </Button>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <>
      <PageSurface
        icon={icon}
        title={title}
        actions={<Button onClick={() => setCreating(true)}>New Connection</Button>}
      >
        <div className="flex min-h-0 flex-1 flex-col">
          <DataTable<Connection>
            data={rows}
            columns={columns}
            keyExtractor={(c) => c.id}
            loading={loading}
            emptyTitle="No connections yet"
            emptyDescription="Create a provider connection to wire campaigns to Bolna, WATI, LSQ, or SMS providers."
          />
        </div>
      </PageSurface>

      <Modal
        isOpen={creating}
        onClose={() => setCreating(false)}
        title="New Connection"
      >
        {creating ? (
          <ConnectionForm
            appId={APP_ID}
            onClose={() => setCreating(false)}
            onSaved={() => {
              setCreating(false);
              void refresh();
            }}
          />
        ) : null}
      </Modal>

      <Modal
        isOpen={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={editing ? `Edit ${editing.name}` : ''}
      >
        {editing ? (
          <ConnectionForm
            appId={APP_ID}
            existing={editing}
            onClose={() => setEditing(null)}
            onSaved={() => {
              setEditing(null);
              void refresh();
            }}
          />
        ) : null}
      </Modal>

      <ConfirmDialog
        isOpen={Boolean(archiveTarget)}
        onClose={() => setArchiveTarget(null)}
        onConfirm={handleArchive}
        title="Archive connection"
        description={
          archiveTarget
            ? `Archive "${archiveTarget.name}"? Webhooks for this connection will stop matching incoming requests immediately. Workflows referencing it will fail until rebound.`
            : ''
        }
        confirmLabel="Archive"
        variant="danger"
      />
    </>
  );
}
