import { useState, useEffect, useCallback, useId, useMemo } from 'react';
import { Link2, Copy, Check, Trash2, Plus, SearchX, X } from 'lucide-react';
import {
  Button,
  Badge,
  LoadingState,
  ConfirmDialog,
  Select,
  TableToolbar,
  DataTable,
  type ColumnDef,
} from '@/components/ui';
import type { SelectOption } from '@/components/ui';
import { adminApi } from '@/services/api/adminApi';
import type { InviteLink, CreateInviteLinkRequest, CreateInviteLinkResponse } from '@/services/api/adminApi';
import { rolesApi } from '@/services/api/rolesApi';
import type { RoleResponse } from '@/services/api/rolesApi';
import { notificationService } from '@/services/notifications';
import { useRightOverlay } from '@/hooks';
import { PermissionGate } from '@/components/auth/PermissionGate';

const DEFAULT_PAGE_SIZE = 25;

const EXPIRY_OPTIONS = [
  { label: '1 hour', value: 1 },
  { label: '24 hours', value: 24 },
  { label: '7 days', value: 168 },
  { label: '30 days', value: 720 },
];

type LinkStatus = { label: string; variant: 'success' | 'neutral' | 'warning' };

function statusFor(link: InviteLink): LinkStatus {
  const expired = new Date(link.expiresAt) < new Date();
  const exhausted = link.maxUses !== null && link.usesCount >= link.maxUses;
  if (!link.isActive) return { label: 'Revoked', variant: 'neutral' };
  if (expired) return { label: 'Expired', variant: 'neutral' };
  if (exhausted) return { label: 'Exhausted', variant: 'warning' };
  return { label: 'Active', variant: 'success' };
}

export function InviteLinksSection() {
  const [links, setLinks] = useState<InviteLink[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [revokingLink, setRevokingLink] = useState<InviteLink | null>(null);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [allRoles, setAllRoles] = useState<RoleResponse[]>([]);

  // Create form state
  const [showCreateForm, setShowCreateForm] = useState(false);
  const createTitleId = useId();
  const createAriaProps = useRightOverlay(showCreateForm, {
    onClose: () => setShowCreateForm(false),
    labelledBy: createTitleId,
  });
  const [label, setLabel] = useState('');
  const [roleId, setRoleId] = useState('');
  const [roles, setRoles] = useState<RoleResponse[]>([]);
  const [maxUses, setMaxUses] = useState('');
  const [expiresInHours, setExpiresInHours] = useState(168);

  // One-time URL display
  const [generatedUrl, setGeneratedUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const loadLinks = useCallback(async () => {
    try {
      const data = await adminApi.listInviteLinks();
      setLinks(data);
    } catch {
      notificationService.error('Failed to load invite links');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { loadLinks(); }, [loadLinks]);
  useEffect(() => { setPage(1); }, [search]);
  useEffect(() => {
    rolesApi.listRoles().then((all) => {
      setAllRoles(all);
      const filtered = all.filter((r) => !r.isSystem);
      setRoles(filtered);
      if (filtered.length > 0) setRoleId(filtered[0].id);
    });
  }, []);

  const roleNamesById = useMemo(() => {
    const map = new Map<string, string>();
    for (const r of allRoles) map.set(r.id, r.name);
    return map;
  }, [allRoles]);

  const roleOptions = useMemo<SelectOption[]>(
    () => roles.map((role) => ({ value: role.id, label: role.name })),
    [roles],
  );

  const expiryOptions = useMemo<SelectOption[]>(
    () => EXPIRY_OPTIONS.map((option) => ({ value: String(option.value), label: option.label })),
    [],
  );

  const filtered = useMemo(() => {
    if (!search.trim()) return links;
    const q = search.toLowerCase();
    return links.filter(
      (l) =>
        (l.label ?? '').toLowerCase().includes(q) ||
        l.roleId.toLowerCase().includes(q) ||
        (roleNamesById.get(l.roleId) ?? '').toLowerCase().includes(q) ||
        l.createdByEmail.toLowerCase().includes(q) ||
        statusFor(l).label.toLowerCase().includes(q),
    );
  }, [links, search, roleNamesById]);

  const totalItems = filtered.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const safePage = Math.min(page, totalPages);
  const paginated = filtered.slice((safePage - 1) * pageSize, safePage * pageSize);

  const handleCreate = async () => {
    setIsCreating(true);
    try {
      const body: CreateInviteLinkRequest = { roleId, expiresInHours };
      if (label.trim()) body.label = label.trim();
      if (maxUses.trim()) body.maxUses = parseInt(maxUses, 10);

      const result: CreateInviteLinkResponse = await adminApi.createInviteLink(body);
      setGeneratedUrl(result.inviteUrl);
      setCopied(false);
      setShowCreateForm(false);
      setLabel('');
      setMaxUses('');
      setRoleId(roles.length > 0 ? roles[0].id : '');
      setExpiresInHours(168);
      await loadLinks();
    } catch {
      notificationService.error('Failed to create invite link');
    } finally {
      setIsCreating(false);
    }
  };

  const handleRevoke = async () => {
    if (!revokingLink) return;
    try {
      await adminApi.revokeInviteLink(revokingLink.id);
      notificationService.success('Invite link revoked');
      setRevokingLink(null);
      await loadLinks();
    } catch {
      notificationService.error('Failed to revoke invite link');
    }
  };

  const handleCopy = () => {
    if (!generatedUrl) return;
    navigator.clipboard.writeText(generatedUrl);
    setCopied(true);
    notificationService.success('Link copied to clipboard');
    setTimeout(() => setCopied(false), 2000);
  };

  const inputClass = 'w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--color-brand-accent)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)]';

  const columns = useMemo((): ColumnDef<InviteLink>[] => [
    {
      key: 'label',
      header: 'Label',
      width: 'min-w-[180px]',
      render: (link) =>
        link.label ? link.label : <span className="italic text-[var(--text-muted)]">No label</span>,
    },
    {
      key: 'role',
      header: 'Role',
      width: 'min-w-[160px]',
      render: (link) => {
        const name = roleNamesById.get(link.roleId);
        return (
          <span title={link.roleId}>
            <Badge variant="neutral" size="sm">
              {name ?? link.roleId.slice(0, 8)}
            </Badge>
          </span>
        );
      },
    },
    {
      key: 'uses',
      header: 'Uses',
      width: 'w-[90px]',
      render: (link) => (
        <span className="tabular-nums text-[var(--text-secondary)]">
          {link.usesCount}{link.maxUses !== null ? ` / ${link.maxUses}` : ''}
        </span>
      ),
    },
    {
      key: 'expires',
      header: 'Expires',
      width: 'w-[170px]',
      render: (link) => (
        <span className="tabular-nums text-[var(--text-muted)]">
          {new Date(link.expiresAt).toLocaleDateString(undefined, {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          })}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      width: 'w-[110px]',
      render: (link) => {
        const status = statusFor(link);
        return <Badge variant={status.variant} dot={status.variant} size="sm">{status.label}</Badge>;
      },
    },
    {
      key: 'actions',
      header: 'Actions',
      width: 'w-[100px]',
      cellClassName: 'text-right',
      headerClassName: 'text-right',
      render: (link) =>
        link.isActive ? (
          <PermissionGate action="invite_link:manage">
            <Button
              variant="danger"
              size="sm"
              icon={Trash2}
              iconOnly
              title="Revoke"
              onClick={(e) => {
                e.stopPropagation();
                setRevokingLink(link);
              }}
            />
          </PermissionGate>
        ) : null,
    },
  ], [roleNamesById]);

  if (isLoading) {
    return <LoadingState />;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      {generatedUrl && (
        <div className="rounded-lg border border-[var(--color-brand-accent)]/30 bg-[var(--color-brand-accent)]/5 p-3">
          <p className="mb-2 text-[13px] font-medium text-[var(--text-primary)]">
            Invite link generated — copy it now, it won&apos;t be shown again.
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 truncate rounded bg-[var(--bg-primary)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)] border border-[var(--border-subtle)]">
              {generatedUrl}
            </code>
            <Button size="sm" variant="secondary" icon={copied ? Check : Copy} onClick={handleCopy}>
              {copied ? 'Copied' : 'Copy'}
            </Button>
          </div>
        </div>
      )}

      <TableToolbar
        search={{
          value: search,
          onChange: setSearch,
          placeholder: 'Search invite links…',
          label: 'Search invite links',
        }}
        actions={
          <PermissionGate action="invite_link:manage">
            <Button size="sm" icon={Plus} onClick={() => { setShowCreateForm(true); setGeneratedUrl(null); }}>
              Generate Invite Link
            </Button>
          </PermissionGate>
        }
      />

      <DataTable
        columns={columns}
        data={paginated}
        keyExtractor={(link) => link.id}
        pagination={{
          page: safePage,
          totalPages,
          pageSize,
          totalItems,
          showCount: true,
          onPageChange: setPage,
          onPageSizeChange: (n) => {
            setPageSize(n);
            setPage(1);
          },
        }}
        emptyIcon={search ? SearchX : Link2}
        emptyTitle={search ? 'No results found' : 'No invite links yet'}
        emptyDescription={
          search
            ? `No invite links match "${search}"`
            : 'Generate an invite link to let team members sign up'
        }
      />

      {showCreateForm && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="absolute inset-0 bg-black/40" onClick={() => setShowCreateForm(false)} />
          <div {...createAriaProps} className="relative w-full max-w-md bg-[var(--bg-primary)] shadow-xl flex flex-col animate-in slide-in-from-right duration-200">
            <div className="flex items-center justify-between border-b border-[var(--border-default)] px-5 py-4">
              <h2 id={createTitleId} className="text-base font-semibold text-[var(--text-primary)]">Generate Invite Link</h2>
              <button onClick={() => setShowCreateForm(false)} className="rounded-md p-1 text-[var(--text-muted)] hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)] transition-colors">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
              <div>
                <label className="mb-1 block text-[13px] font-medium text-[var(--text-secondary)]">Label (optional)</label>
                <input type="text" value={label} onChange={(e) => setLabel(e.target.value)} className={inputClass} placeholder="e.g. Engineering team" />
              </div>
              <div>
                <label className="mb-1 block text-[13px] font-medium text-[var(--text-secondary)]">Role</label>
                <Select
                  value={roleId}
                  onChange={setRoleId}
                  options={roleOptions}
                  className="w-full"
                />
              </div>
              <div>
                <label className="mb-1 block text-[13px] font-medium text-[var(--text-secondary)]">Max Uses</label>
                <input type="number" min="1" value={maxUses} onChange={(e) => setMaxUses(e.target.value)} className={inputClass} placeholder="Unlimited" />
              </div>
              <div>
                <label className="mb-1 block text-[13px] font-medium text-[var(--text-secondary)]">Expires In</label>
                <Select
                  value={String(expiresInHours)}
                  onChange={(value) => setExpiresInHours(Number(value))}
                  options={expiryOptions}
                  className="w-full"
                />
              </div>
            </div>
            <div className="border-t border-[var(--border-default)] px-5 py-3 flex justify-end gap-2">
              <Button type="button" variant="secondary" size="md" onClick={() => setShowCreateForm(false)}>Cancel</Button>
              <Button size="md" onClick={handleCreate} isLoading={isCreating} icon={Link2}>Generate Invite Link</Button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        isOpen={!!revokingLink}
        title="Revoke Invite Link"
        description={`Are you sure you want to revoke this invite link${revokingLink?.label ? ` (${revokingLink.label})` : ''}? It will no longer be usable for signups.`}
        confirmLabel="Revoke"
        variant="danger"
        onConfirm={handleRevoke}
        onClose={() => setRevokingLink(null)}
      />
    </div>
  );
}
