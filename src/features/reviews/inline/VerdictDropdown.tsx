import { Select } from '@/components/ui';
import { BeforeAfterChip } from './BeforeAfterChip';

interface VerdictDropdownProps {
  originalValue: string | null;
  value: string | null;
  allowedValues: string[];
  isEditing: boolean;
  color?: string;
  onChange: (nextValue: string) => void;
}

export function VerdictDropdown({
  originalValue,
  value,
  allowedValues,
  isEditing,
  color,
  onChange,
}: VerdictDropdownProps) {
  const currentValue = value ?? originalValue ?? allowedValues[0] ?? '';

  if (!isEditing) {
    if (originalValue && value && originalValue !== value) {
      return <BeforeAfterChip before={originalValue} after={value} category="status" />;
    }

    return (
      <span className="text-sm font-semibold leading-none" style={{ color: color || 'var(--text-primary)' }}>
        {currentValue || '—'}
      </span>
    );
  }

  return (
    <div className="flex min-w-[160px] flex-col items-center gap-1">
      {originalValue && (
        <span className="text-[10px] text-[var(--text-muted)]">
          AI: <span className="font-semibold text-[var(--text-secondary)]">{originalValue}</span>
        </span>
      )}
      <Select
        value={currentValue}
        onChange={onChange}
        options={allowedValues.map((allowedValue) => ({ value: allowedValue, label: allowedValue }))}
        size="sm"
        className="min-w-[140px]"
      />
    </div>
  );
}
