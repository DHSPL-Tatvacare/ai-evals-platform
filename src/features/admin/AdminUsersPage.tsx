import { useState, useEffect, useCallback } from 'react';
import { Plus, Pencil, UserX } from 'lucide-react';
import { Button, Badge, Spinner, ConfirmDialog } from '@/components/ui';
import { adminApi } from '@/services/api/adminApi';
import type { AdminUser, UpdateUserRequest } from '@/services/api/adminApi';
import { useAuthStore } from '@/stores/authStore';
import { notificationService } from '@/services/notifications';
import { cn } from '@/utils';
import { CreateUserDialog } from './CreateUserDialog';
import { EditUserDialog } from './EditUserDialog';

const roleBadgeVariant = (role: string) => {
  switch (role) {
    case 'owner': return 'primary' as const;
    case 'admin': return 'info' as const;
    default: return 'neutral' as const;
  }
};

export function AdminUsersPage() {
  const currentUser = useAuthStore((s) => s.user);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null);
  const [deactivatingUser, setDeactivatingUser] = useState<AdminUser | null>(null);

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

  const handleCreateUser = async (data: {
    email: string;
    displayName: string;
    password: string;
    role: 'admin' | 'member';
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
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    );
  }

  const isOwner = currentUser?.role === 'owner';

  return (
    <div className="mx-auto max-w-4xl p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[var(--text-primary)]">
            User Management
          </h1>
          <p className="mt-1 text-[13px] text-[var(--text-muted)]">
            Manage users in your organization
          </p>
        </div>
        <Button size="md" onClick={() => setIsCreateOpen(true)} icon={Plus}>
          Add User
        </Button>
      </div>

      <div className="overflow-hidden rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)]">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
              <th className="px-4 py-3 text-left text-[12px] font-medium uppercase tracking-wider text-[var(--text-muted)]">
                Name
              </th>
              <th className="px-4 py-3 text-left text-[12px] font-medium uppercase tracking-wider text-[var(--text-muted)]">
                Email
              </th>
              <th className="px-4 py-3 text-left text-[12px] font-medium uppercase tracking-wider text-[var(--text-muted)]">
                Role
              </th>
              <th className="px-4 py-3 text-left text-[12px] font-medium uppercase tracking-wider text-[var(--text-muted)]">
                Status
              </th>
              <th className="px-4 py-3 text-right text-[12px] font-medium uppercase tracking-wider text-[var(--text-muted)]">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--border-subtle)]">
            {users.map((user) => {
              const isSelf = user.id === currentUser?.id;
              return (
                <tr
                  key={user.id}
                  className={cn(
                    'transition-colors hover:bg-[var(--bg-secondary)]/50',
                    !user.isActive && 'opacity-60',
                  )}
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--color-brand-accent)]/20 text-[11px] font-semibold text-[var(--text-brand)]">
                        {user.displayName
                          .split(' ')
                          .map((n) => n[0])
                          .join('')
                          .toUpperCase()
                          .slice(0, 2)}
                      </div>
                      <span className="text-[13px] font-medium text-[var(--text-primary)]">
                        {user.displayName}
                        {isSelf && (
                          <span className="ml-1.5 text-[11px] text-[var(--text-muted)]">
                            (you)
                          </span>
                        )}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-[13px] text-[var(--text-secondary)]">
                    {user.email}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={roleBadgeVariant(user.role)} size="sm">
                      {user.role}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <Badge
                      variant={user.isActive ? 'success' : 'neutral'}
                      dot={user.isActive ? 'success' : 'neutral'}
                      size="sm"
                    >
                      {user.isActive ? 'Active' : 'Disabled'}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={Pencil}
                        iconOnly
                        title="Edit user"
                        onClick={() => setEditingUser(user)}
                      />
                      {isOwner && !isSelf && user.role !== 'owner' && user.isActive && (
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={UserX}
                          iconOnly
                          title="Deactivate user"
                          onClick={() => setDeactivatingUser(user)}
                        />
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {users.length === 0 && (
          <div className="py-12 text-center text-[13px] text-[var(--text-muted)]">
            No users found
          </div>
        )}
      </div>

      <CreateUserDialog
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onSubmit={handleCreateUser}
      />

      <EditUserDialog
        isOpen={!!editingUser}
        user={editingUser}
        currentUserId={currentUser?.id ?? ''}
        currentUserRole={currentUser?.role ?? 'member'}
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
    </div>
  );
}
