import { useState, useEffect, useCallback, useMemo } from 'react';
import { Plus, Pencil, UserX, KeyRound, Search, Users, SearchX } from 'lucide-react';
import { Button, Badge, Spinner, ConfirmDialog, Tabs, EmptyState } from '@/components/ui';
import { adminApi } from '@/services/api/adminApi';
import type { AdminUser, UpdateUserRequest } from '@/services/api/adminApi';
import { useAuthStore } from '@/stores/authStore';
import { notificationService } from '@/services/notifications';
import { cn } from '@/utils';
import { PermissionGate } from '@/components/auth/PermissionGate';
import { CreateUserDialog } from './CreateUserDialog';
import { EditUserDialog } from './EditUserDialog';
import { ResetPasswordDialog } from './ResetPasswordDialog';
import { InviteLinksSection } from './InviteLinksSection';
import { RolesTab } from './RolesTab';
import { AuditLogTab } from './AuditLogTab';

const ROWS_PER_PAGE = 20;


function UsersTab() {
  const currentUser = useAuthStore((s) => s.user);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null);
  const [deactivatingUser, setDeactivatingUser] = useState<AdminUser | null>(null);
  const [resetPasswordUser, setResetPasswordUser] = useState<AdminUser | null>(null);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);

  const loadUsers = useCallback(async () => {
    try {
      const data = await adminApi.listUsers();
      setUsers(data);
    } catch {
      notificationService.error('Failed to load users');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  const filtered = useMemo(() => {
    if (!search.trim()) return users;
    const q = search.toLowerCase();
    return users.filter(
      (u) =>
        u.displayName.toLowerCase().includes(q) ||
        u.email.toLowerCase().includes(q) ||
        u.roleName.toLowerCase().includes(q),
    );
  }, [users, search]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / ROWS_PER_PAGE));
  const paginated = filtered.slice((page - 1) * ROWS_PER_PAGE, page * ROWS_PER_PAGE);

  // Reset to page 1 when search changes
  useEffect(() => { setPage(1); }, [search]);

  const handleCreateUser = async (data: {
    email: string;
    displayName: string;
    password: string;
    roleId: string;
  }) => {
    await adminApi.createUser(data);
    notificationService.success('User created');
    await loadUsers();
  };

  const handleUpdateUser = async (userId: string, data: UpdateUserRequest) => {
    await adminApi.updateUser(userId, data);
    notificationService.success('User updated');
    await loadUsers();
  };

  const handleDeactivateUser = () => {
    if (!deactivatingUser) return;
    adminApi.deactivateUser(deactivatingUser.id).then(() => {
      notificationService.success('User deactivated');
      setDeactivatingUser(null);
      loadUsers();
    }).catch(() => {
      notificationService.error('Failed to deactivate user');
    });
  };

  if (isLoading) {
    return (
      <div className="flex h-40 items-center justify-center">
        <Spinner />
      </div>
    );
  }

  const isOwner = currentUser?.isOwner;

  return (
    <>
      {/* Toolbar: search + add */}
      <div className="mb-4 flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name, email, or role..."
            className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] py-2 pl-9 pr-3 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--color-brand-accent)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)] transition-colors"
          />
        </div>
        <PermissionGate action="user:create">
          <Button size="md" onClick={() => setIsCreateOpen(true)} icon={Plus}>
            Add User
          </Button>
        </PermissionGate>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)]">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
              <th className="px-4 py-2.5 text-left text-[11px] font-medium uppercase tracking-wider text-[var(--text-muted)]">Name</th>
              <th className="px-4 py-2.5 text-left text-[11px] font-medium uppercase tracking-wider text-[var(--text-muted)]">Email</th>
              <th className="px-4 py-2.5 text-left text-[11px] font-medium uppercase tracking-wider text-[var(--text-muted)]">Role</th>
              <th className="px-4 py-2.5 text-left text-[11px] font-medium uppercase tracking-wider text-[var(--text-muted)]">Status</th>
              <th className="px-4 py-2.5 text-right text-[11px] font-medium uppercase tracking-wider text-[var(--text-muted)]">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--border-subtle)]">
            {paginated.map((user) => {
              const isSelf = user.id === currentUser?.id;
              return (
                <tr
                  key={user.id}
                  className={cn(
                    'transition-colors hover:bg-[var(--bg-secondary)]/50',
                    !user.isActive && 'opacity-60',
                  )}
                >
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-3">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-brand-accent)]/20 text-[10px] font-semibold text-[var(--text-brand)]">
                        {user.displayName.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2)}
                      </div>
                      <span className="text-[13px] font-medium text-[var(--text-primary)]">
                        {user.displayName}
                        {isSelf && <span className="ml-1.5 text-[11px] text-[var(--text-muted)]">(you)</span>}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-[13px] text-[var(--text-secondary)]">{user.email}</td>
                  <td className="px-4 py-2.5">
                    <Badge variant={user.isOwner ? 'warning' : 'info'} size="sm">{user.roleName}</Badge>
                  </td>
                  <td className="px-4 py-2.5">
                    <Badge variant={user.isActive ? 'success' : 'neutral'} dot={user.isActive ? 'success' : 'neutral'} size="sm">
                      {user.isActive ? 'Active' : 'Disabled'}
                    </Badge>
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <PermissionGate action="user:edit">
                        <Button variant="ghost" size="sm" icon={Pencil} iconOnly title="Edit user" onClick={() => setEditingUser(user)} />
                      </PermissionGate>
                      {!isSelf && user.isActive && (
                        <PermissionGate action="user:reset_password">
                          <Button variant="ghost" size="sm" icon={KeyRound} iconOnly title="Reset password" onClick={() => setResetPasswordUser(user)} />
                        </PermissionGate>
                      )}
                      {isOwner && !isSelf && !user.isOwner && user.isActive && (
                        <PermissionGate action="user:deactivate">
                          <Button variant="ghost" size="sm" icon={UserX} iconOnly title="Deactivate user" onClick={() => setDeactivatingUser(user)} />
                        </PermissionGate>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {filtered.length === 0 && (
        <EmptyState
          icon={search ? SearchX : Users}
          title={search ? 'No results found' : 'No users yet'}
          description={search ? `No users match "${search}"` : 'Add your first team member to get started'}
          compact
          className="mt-4"
          action={!search ? { label: 'Add User', onClick: () => setIsCreateOpen(true) } : undefined}
        />
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-3 flex items-center justify-between">
          <p className="text-[12px] text-[var(--text-muted)]">
            Showing {(page - 1) * ROWS_PER_PAGE + 1}–{Math.min(page * ROWS_PER_PAGE, filtered.length)} of {filtered.length}
          </p>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <span className="px-2 text-[12px] text-[var(--text-secondary)]">
              {page} / {totalPages}
            </span>
            <Button variant="ghost" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
          </div>
        </div>
      )}

      {/* Dialogs */}
      <CreateUserDialog
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onSubmit={handleCreateUser}
      />
      <EditUserDialog
        isOpen={!!editingUser}
        user={editingUser}
        currentUserId={currentUser?.id ?? ''}
        onClose={() => setEditingUser(null)}
        onSubmit={handleUpdateUser}
      />
      <ConfirmDialog
        isOpen={!!deactivatingUser}
        title="Deactivate User"
        description={`Are you sure you want to deactivate ${deactivatingUser?.displayName}? They will no longer be able to log in.`}
        confirmLabel="Deactivate"
        variant="danger"
        onConfirm={handleDeactivateUser}
        onClose={() => setDeactivatingUser(null)}
      />
      <ResetPasswordDialog
        isOpen={!!resetPasswordUser}
        user={resetPasswordUser}
        onClose={() => setResetPasswordUser(null)}
        onSuccess={() => notificationService.success('Password reset successfully')}
      />
    </>
  );
}

export function AdminUsersPage() {
  const tabs = [
    {
      id: 'users',
      label: 'Users',
      content: <UsersTab />,
    },
    {
      id: 'invites',
      label: 'Invite Links',
      content: <InviteLinksSection />,
    },
    {
      id: 'roles',
      label: 'Roles',
      content: <RolesTab />,
    },
    {
      id: 'security',
      label: 'Security',
      content: <AuditLogTab />,
    },
  ];

  return (
    <div className="pb-20">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-[var(--text-primary)]">
          Admin
        </h1>
        <p className="mt-1 text-[13px] text-[var(--text-muted)]">
          Manage users, access, and security for your organization
        </p>
      </div>
      <Tabs tabs={tabs} defaultTab="users" />
    </div>
  );
}
