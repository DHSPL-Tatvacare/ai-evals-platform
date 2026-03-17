import { useState, useEffect } from 'react';
import { Modal, Button, Input } from '@/components/ui';
import type { AdminUser, UpdateUserRequest } from '@/services/api/adminApi';

interface EditUserDialogProps {
  isOpen: boolean;
  user: AdminUser | null;
  currentUserId: string;
  currentUserRole: string;
  onClose: () => void;
  onSubmit: (userId: string, data: UpdateUserRequest) => Promise<void>;
}

export function EditUserDialog({
  isOpen,
  user,
  currentUserId,
  currentUserRole,
  onClose,
  onSubmit,
}: EditUserDialogProps) {
  const [displayName, setDisplayName] = useState('');
  const [role, setRole] = useState<'admin' | 'member'>('member');
  const [isActive, setIsActive] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (user) {
      setDisplayName(user.displayName);
      setRole(user.role === 'owner' ? 'admin' : user.role);
      setIsActive(user.isActive);
      setError('');
    }
  }, [user]);

  if (!user) return null;

  const isSelf = user.id === currentUserId;
  const isOwnerUser = user.role === 'owner';
  const canChangeRole = !isSelf && !isOwnerUser;
  const canToggleActive = !isSelf && currentUserRole === 'owner';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!displayName.trim()) {
      setError('Display name is required');
      return;
    }

    const updates: UpdateUserRequest = {};
    if (displayName.trim() !== user.displayName) {
      updates.displayName = displayName.trim();
    }
    if (canChangeRole && role !== user.role) {
      updates.role = role;
    }
    if (canToggleActive && isActive !== user.isActive) {
      updates.isActive = isActive;
    }

    if (Object.keys(updates).length === 0) {
      onClose();
      return;
    }

    setIsSubmitting(true);
    setError('');
    try {
      await onSubmit(user.id, updates);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update user');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Edit User">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="mb-1 block text-[13px] font-medium text-[var(--text-secondary)]">
            Email
          </label>
          <Input value={user.email} disabled />
        </div>
        <div>
          <label className="mb-1 block text-[13px] font-medium text-[var(--text-secondary)]">
            Display Name
          </label>
          <Input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            autoFocus
          />
        </div>
        <div>
          <label className="mb-1 block text-[13px] font-medium text-[var(--text-secondary)]">
            Role
          </label>
          {isOwnerUser ? (
            <Input value="Owner" disabled />
          ) : (
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as 'admin' | 'member')}
              disabled={!canChangeRole}
              className="h-9 w-full rounded-[6px] border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 text-[14px] text-[var(--text-primary)] transition-colors focus:border-[var(--border-focus)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-accent)]/50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <option value="member">Member</option>
              <option value="admin">Admin</option>
            </select>
          )}
          {isSelf && (
            <p className="mt-1 text-[11px] text-[var(--text-muted)]">
              You cannot change your own role
            </p>
          )}
        </div>
        {canToggleActive && (
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="user-active"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="h-4 w-4 rounded border-[var(--border-default)] text-[var(--color-brand-accent)] focus:ring-[var(--color-brand-accent)]"
            />
            <label
              htmlFor="user-active"
              className="text-[13px] font-medium text-[var(--text-secondary)]"
            >
              Account active
            </label>
          </div>
        )}

        {error && (
          <p className="text-[13px] text-[var(--color-error)]">{error}</p>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" size="md" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" size="md" isLoading={isSubmitting}>
            Save Changes
          </Button>
        </div>
      </form>
    </Modal>
  );
}
