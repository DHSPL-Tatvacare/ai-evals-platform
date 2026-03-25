import { useState, useEffect } from 'react';
import { Modal, Button, Input, PasswordStrengthIndicator, validatePasswordStrength } from '@/components/ui';
import { rolesApi } from '@/services/api/rolesApi';
import type { RoleResponse } from '@/services/api/rolesApi';

interface CreateUserDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: {
    email: string;
    displayName: string;
    password: string;
    roleId: string;
  }) => Promise<void>;
}

export function CreateUserDialog({ isOpen, onClose, onSubmit }: CreateUserDialogProps) {
  const [email, setEmail] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [roleId, setRoleId] = useState('');
  const [roles, setRoles] = useState<RoleResponse[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    rolesApi.listRoles().then((all) => {
      const filtered = all.filter((r) => !r.isSystem);
      setRoles(filtered);
      if (filtered.length > 0) setRoleId(filtered[0].id);
    });
  }, []);

  const resetForm = () => {
    setEmail('');
    setDisplayName('');
    setPassword('');
    setRoleId(roles.length > 0 ? roles[0].id : '');
    setError('');
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  const { valid: passwordStrong } = validatePasswordStrength(password);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !displayName.trim() || !password.trim()) {
      setError('All fields are required');
      return;
    }
    if (!passwordStrong) {
      setError('Password does not meet strength requirements');
      return;
    }

    setIsSubmitting(true);
    setError('');
    try {
      await onSubmit({ email: email.trim(), displayName: displayName.trim(), password, roleId });
      resetForm();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create user');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Add User">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="mb-1 block text-[13px] font-medium text-[var(--text-secondary)]">
            Email
          </label>
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="user@example.com"
            autoFocus
          />
        </div>
        <div>
          <label className="mb-1 block text-[13px] font-medium text-[var(--text-secondary)]">
            Display Name
          </label>
          <Input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="Full name"
          />
        </div>
        <div>
          <label className="mb-1 block text-[13px] font-medium text-[var(--text-secondary)]">
            Temporary Password
          </label>
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Create a strong password"
          />
          <PasswordStrengthIndicator password={password} className="mt-2" />
        </div>
        <div>
          <label className="mb-1 block text-[13px] font-medium text-[var(--text-secondary)]">
            Role
          </label>
          <select
            value={roleId}
            onChange={(e) => setRoleId(e.target.value)}
            className="h-9 w-full rounded-[6px] border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 text-[14px] text-[var(--text-primary)] transition-colors focus:border-[var(--border-focus)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-accent)]/50"
          >
            {roles.map((r) => (
              <option key={r.id} value={r.id}>{r.name}</option>
            ))}
          </select>
        </div>

        {error && (
          <p className="text-[13px] text-[var(--color-error)]">{error}</p>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" size="md" onClick={handleClose}>
            Cancel
          </Button>
          <Button type="submit" size="md" isLoading={isSubmitting} disabled={!passwordStrong}>
            Create User
          </Button>
        </div>
      </form>
    </Modal>
  );
}
