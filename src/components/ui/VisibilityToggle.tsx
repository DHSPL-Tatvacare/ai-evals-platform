import { Globe2, Lock } from 'lucide-react';
import { cn } from '@/utils';
import type { AssetVisibility } from '@/types';

interface VisibilityToggleProps {
  value: AssetVisibility;
  onChange: (value: AssetVisibility) => void;
  disabled?: boolean;
}

const OPTIONS: Array<{
  value: AssetVisibility;
  label: string;
  icon: typeof Lock;
}> = [
  { value: 'private', label: 'Private', icon: Lock },
  { value: 'shared', label: 'Shared', icon: Globe2 },
];

export function VisibilityToggle({ value, onChange, disabled = false }: VisibilityToggleProps) {
  return (
    <div className="inline-flex rounded-[8px] border border-[var(--border-default)] bg-[var(--bg-secondary)] p-1">
      {OPTIONS.map((option) => {
        const Icon = option.icon;
        const isActive = value === option.value;
        return (
          <button
            key={option.value}
            type="button"
            disabled={disabled}
            onClick={() => onChange(option.value)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-[6px] px-3 py-1.5 text-[12px] font-medium transition-colors',
              isActive
                ? 'bg-[var(--interactive-primary)] text-[var(--text-on-color)]'
                : 'text-[var(--text-secondary)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)]',
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
