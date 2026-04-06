import { useMemo } from 'react';
import * as Select from '@radix-ui/react-select';
import { Check, ChevronDown } from 'lucide-react';

import { cn } from '@/utils';

export interface SingleSelectOption {
  value: string;
  label: string;
}

interface SingleSelectProps {
  value: string;
  onChange: (value: string) => void;
  options: SingleSelectOption[];
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  size?: 'sm' | 'md';
}

export function SingleSelect({
  value,
  onChange,
  options,
  placeholder = 'Select...',
  className,
  disabled = false,
  size = 'md',
}: SingleSelectProps) {
  const selectedOption = useMemo(
    () => options.find((option) => option.value === value),
    [options, value],
  );

  return (
    <Select.Root
      value={value || undefined}
      onValueChange={onChange}
      disabled={disabled}
    >
      <Select.Trigger
        className={cn(
          'w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)]',
          'flex items-center justify-between gap-2 text-left text-[var(--text-primary)]',
          size === 'sm' ? 'h-7 px-2.5 text-[13px]' : 'h-9 px-3 text-[13px]',
          'focus:border-[var(--border-focus)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-accent)]/50',
          'disabled:cursor-not-allowed disabled:opacity-50',
          className,
        )}
        title={selectedOption?.label}
        aria-label={selectedOption?.label ?? placeholder}
      >
        <Select.Value
          placeholder={<span className="text-[var(--text-muted)]">{placeholder}</span>}
        />
        <Select.Icon asChild>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-[var(--text-muted)]" />
        </Select.Icon>
      </Select.Trigger>

      <Select.Portal>
        <Select.Content
          position="popper"
          sideOffset={4}
          className={cn(
            'z-[9999] overflow-hidden rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] py-1 shadow-lg',
            'min-w-[220px] w-[var(--radix-select-trigger-width)] max-h-[280px]',
          )}
        >
          <Select.Viewport>
            {options.map((option) => (
              <Select.Item
                key={option.value}
                value={option.value}
                className={cn(
                  'relative flex w-full cursor-default items-center justify-between gap-3 px-3 py-2 text-[13px] outline-none transition-colors',
                  'text-[var(--text-primary)] hover:bg-[var(--bg-hover)] focus:bg-[var(--bg-hover)]',
                  'data-[state=checked]:bg-[var(--surface-brand-subtle)] data-[state=checked]:text-[var(--text-brand)]',
                )}
              >
                <Select.ItemText>
                  <span className="truncate">{option.label}</span>
                </Select.ItemText>
                <Select.ItemIndicator>
                  <span className="flex h-4 w-4 shrink-0 items-center justify-center">
                    <Check className="h-3.5 w-3.5 text-[var(--text-brand)]" />
                  </span>
                </Select.ItemIndicator>
              </Select.Item>
            ))}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}
