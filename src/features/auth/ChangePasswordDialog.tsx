import { useState } from 'react';
import { Modal, Button, Input, PasswordStrengthIndicator, validatePasswordStrength } from '@/components/ui';
import { authApi } from '@/services/api/authApi';
import { notificationService } from '@/services/notifications';

interface ChangePasswordDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ChangePasswordDialog({ isOpen, onClose }: ChangePasswordDialogProps) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleClose = () => {
    setCurrentPassword('');
    setNewPassword('');
    setConfirmPassword('');
    setError('');
    onClose();
  };

  const { valid: passwordStrong } = validatePasswordStrength(newPassword);

  const canSubmit =
    currentPassword.length > 0 &&
    passwordStrong &&
    newPassword === confirmPassword &&
    currentPassword !== newPassword &&
    !isSubmitting;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;

    setIsSubmitting(true);
    setError('');
    try {
      await authApi.changePassword(currentPassword, newPassword);
      notificationService.success('Password changed successfully');
      handleClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to change password');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Change Password">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="mb-1 block text-[13px] font-medium text-[var(--text-secondary)]">
            Current Password
          </label>
          <Input
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            placeholder="Enter current password"
            autoFocus
          />
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
          />
          <PasswordStrengthIndicator password={newPassword} className="mt-2" />
          {currentPassword && newPassword && currentPassword === newPassword && (
            <p className="mt-1 text-[11px] text-red-400">New password must be different from current password</p>
          )}
        </div>
        <div>
          <label className="mb-1 block text-[13px] font-medium text-[var(--text-secondary)]">
            Confirm New Password
          </label>
          <Input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="Re-enter new password"
          />
          {confirmPassword.length > 0 && newPassword !== confirmPassword && (
            <p className="mt-1 text-[11px] text-red-400">Passwords do not match</p>
          )}
        </div>

        {error && (
          <p className="text-[13px] text-[var(--color-error)]">{error}</p>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" size="md" onClick={handleClose}>
            Cancel
          </Button>
          <Button type="submit" size="md" disabled={!canSubmit} isLoading={isSubmitting}>
            Change Password
          </Button>
        </div>
      </form>
    </Modal>
  );
}
