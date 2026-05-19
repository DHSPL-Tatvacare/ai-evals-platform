import { Button } from '@/components/ui/Button';
import { emailSettingsCopy } from '../emailSettings.copy';

interface Props {
  recipientEmail: string;
  onChange: () => void;
}

export function RecipientAddressRow({ recipientEmail, onChange }: Props) {
  return (
    <section className="rounded-[12px] border border-[var(--border-default)] bg-[var(--bg-primary)] px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-[12px] font-medium uppercase tracking-wide text-[var(--text-secondary)]">
            {emailSettingsCopy.recipientLabel}
          </div>
          <div className="mt-1 truncate text-[14px] font-medium text-[var(--text-primary)]">
            {recipientEmail}
          </div>
          <p className="mt-1 text-[12px] text-[var(--text-tertiary)]">
            {emailSettingsCopy.recipientHint}
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={onChange}>
          {emailSettingsCopy.changeRecipient}
        </Button>
      </div>
    </section>
  );
}
