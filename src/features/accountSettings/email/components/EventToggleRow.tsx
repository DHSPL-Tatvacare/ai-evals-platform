import { Lock } from 'lucide-react';
import { Switch } from '@/components/ui/Switch';
import { cn } from '@/utils/cn';
import { emailSettingsCopy } from '../emailSettings.copy';
import type { NotificationSubscriptionRow } from '../types';

interface Props {
  row: NotificationSubscriptionRow;
  pending: boolean;
  onToggle: (next: boolean) => void;
}

export function EventToggleRow({ row, pending, onToggle }: Props) {
  const label = emailSettingsCopy.events[row.eventType] ?? row.eventType;
  const disabled = row.isRequired || pending;

  return (
    <div
      className={cn(
        'flex items-center justify-between gap-3 rounded-[8px] px-3 py-2.5',
        'transition-colors',
        disabled ? 'opacity-90' : 'hover:bg-[var(--interactive-secondary)]',
      )}
    >
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <span className="truncate text-[13px] text-[var(--text-primary)]">{label}</span>
        {row.isRequired ? (
          <span
            className="inline-flex items-center gap-1 rounded-full bg-[var(--bg-tertiary)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]"
            title={emailSettingsCopy.error.subscriptionLocked}
          >
            <Lock className="h-3 w-3" />
            {emailSettingsCopy.requiredHint}
          </span>
        ) : null}
      </div>
      <Switch
        size="sm"
        checked={row.isActive}
        disabled={disabled}
        onCheckedChange={(next) => onToggle(next)}
        aria-label={label}
      />
    </div>
  );
}
