import { useState } from 'react';
import { X } from 'lucide-react';
import { RightSlideOverShell } from '@/components/ui/RightSlideOverShell';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { emailSettingsCopy } from '../emailSettings.copy';
import { recipientSchema } from '../emailSettings.schema';

interface Props {
  isOpen: boolean;
  currentRecipient: string;
  onClose: () => void;
  onSubmit: (next: string) => Promise<void>;
  submitting: boolean;
}

export function ChangeRecipientOverlay({
  isOpen,
  currentRecipient,
  onClose,
  onSubmit,
  submitting,
}: Props) {
  const [value, setValue] = useState(currentRecipient);
  const [localError, setLocalError] = useState<string | null>(null);

  const trimmed = value.trim();
  const isDirty = trimmed !== currentRecipient.trim();
  const canSave = isDirty && !submitting;

  const handleSave = async () => {
    const parsed = recipientSchema.safeParse({ recipientEmail: trimmed });
    if (!parsed.success) {
      setLocalError(emailSettingsCopy.error.recipientInvalid);
      return;
    }
    setLocalError(null);
    try {
      await onSubmit(parsed.data.recipientEmail);
    } catch {
      // toast surfaces the failure; nothing else to do here
    }
  };

  return (
    <RightSlideOverShell
      isOpen={isOpen}
      onClose={onClose}
      labelledBy="change-recipient-title"
      widthClassName="w-[var(--overlay-width-sm,420px)] max-w-[85vw]"
    >
      <header className="flex items-start justify-between border-b border-[var(--border-subtle)] px-5 py-4">
        <div>
          <h2
            id="change-recipient-title"
            className="text-[15px] font-semibold text-[var(--text-primary)]"
          >
            {emailSettingsCopy.recipientOverlayTitle}
          </h2>
          <p className="mt-1 text-[12px] text-[var(--text-tertiary)]">
            {emailSettingsCopy.recipientOverlaySubtitle}
          </p>
        </div>
        <button
          onClick={onClose}
          className="rounded-md p-1 text-[var(--text-muted)] hover:bg-[var(--interactive-secondary)]"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-4">
        <label className="block">
          <span className="text-[12px] font-medium text-[var(--text-secondary)]">
            {emailSettingsCopy.recipientLabel}
          </span>
          <Input
            type="email"
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              if (localError) setLocalError(null);
            }}
            className="mt-1.5"
            placeholder="name@workspace.com"
            autoFocus
          />
        </label>
        {localError ? (
          <p className="mt-2 text-[12px] text-[var(--color-error)]">{localError}</p>
        ) : null}
      </div>

      <footer className="flex items-center justify-end gap-2 border-t border-[var(--border-subtle)] px-5 py-3">
        <Button variant="ghost" size="sm" onClick={onClose} disabled={submitting}>
          {emailSettingsCopy.recipientOverlayCancel}
        </Button>
        <Button
          variant="primary"
          size="sm"
          onClick={handleSave}
          disabled={!canSave}
          isLoading={submitting}
        >
          {emailSettingsCopy.recipientOverlaySave}
        </Button>
      </footer>
    </RightSlideOverShell>
  );
}
