import { useState } from 'react';
import { Modal, Button, Input, PasswordStrengthIndicator, validatePasswordStrength } from '@/components/ui';
import { adminApi } from '@/services/api/adminApi';
import type { AdminUser } from '@/services/api/adminApi';

interface ResetPasswordDialogProps {
  isOpen: boolean;
  user: AdminUser | null;
  onClose: () => void;
  onSuccess: () => void;
}

export function ResetPasswordDialog({ isOpen, user, onClose, onSuccess }: ResetPasswordDialogProps) {
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleClose = () => {
    setNewPassword('');
    setConfirmPassword('');
    setError('');
    onClose();
  };

  if (!user) return null;

  const { valid: passwordStrong } = validatePasswordStrength(newPassword);

  const canSubmit = passwordStrong && newPassword === confirmPassword && !isSubmitting;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;

    setIsSubmitting(true);
    setError('');
    try {
      await adminApi.resetUserPassword(user.id, newPassword);
      onSuccess();
      handleClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reset password');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Reset Password">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="mb-1 block text-[13px] font-medium text-[var(--text-secondary)]">
            User
          </label>
          <Input value={`${user.displayName} (${user.email})`} disabled />
        </div>
        <div>
          <label className="mb-1 block text-[13px] font-medium text-[var(--text-secondary)]">
            New Password
          </label>
          <Input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="Create a strong password"
            autoFocus
          />
          <PasswordStrengthIndicator password={newPassword} className="mt-2" />
        </div>
        <div>
          <label className="mb-1 block text-[13px] font-medium text-[var(--text-secondary)]">
            Confirm Password
          </label>
          <Input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="Re-enter password"
          />
          {confirmPassword.length > 0 && newPassword !== confirmPassword && (
            <p className="mt-1 text-[11px] text-red-400">Passwords do not match</p>
          )}
        </div>

        <p className="text-[12px] text-[var(--text-muted)]">
          This will immediately invalidate all active sessions for this user.
        </p>

        {error && (
          <p className="text-[13px] text-[var(--color-error)]">{error}</p>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" size="md" onClick={handleClose}>
            Cancel
          </Button>
          <Button type="submit" size="md" disabled={!canSubmit} isLoading={isSubmitting}>
            Reset Password
          </Button>
        </div>
      </form>
    </Modal>
  );
}
