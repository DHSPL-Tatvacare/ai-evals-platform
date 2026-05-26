import { RefreshCw } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { Combobox, type ComboboxOption } from '@/components/ui/Combobox';
import { Input } from '@/components/ui/Input';
import { useProviderPhoneNumbers } from '@/features/orchestration/queries/referenceData';

interface Props {
  /** Connection UUID whose phone numbers are fetched. Falls back to free-text when absent. */
  connectionId?: string;
  value: string;
  onChange(next: string): void;
}

/** Generic phone-number picker backed by the live provider endpoint.
 *  Falls back to a free-text Input when no connection is provided or the list is empty. */
export function ProviderPhoneNumberPicker({ connectionId, value, onChange }: Props) {
  const { data, isFetching, error, refresh } = useProviderPhoneNumbers(connectionId);

  const items = data?.items ?? [];
  const softError: string | null =
    error instanceof Error
      ? error.message
      : (data?.error ?? null);

  // Keep an already-saved number selectable even when absent from the live list.
  const allNumbers = Array.from(
    new Set([...(value ? [value] : []), ...items.map((i) => i.phoneNumber)]),
  );

  const options: ComboboxOption[] = allNumbers.map((num) => {
    const match = items.find((i) => i.phoneNumber === num);
    return {
      value: num,
      label: match?.label ? `${num} · ${match.label}` : num,
    };
  });

  const hasItems = options.length > 0 && (items.length > 0 || Boolean(value));

  if (!connectionId || (!isFetching && !hasItems)) {
    return (
      <div className="flex flex-col gap-1">
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="+911234567890"
        />
        {softError && (
          <p className="text-xs text-[var(--color-error)]">{softError}</p>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <Combobox
            options={options}
            value={value}
            onChange={onChange}
            placeholder={isFetching ? 'Loading numbers…' : 'Select a phone number'}
            disabled={isFetching && items.length === 0}
            loading={isFetching}
          />
        </div>
        <Button
          variant="secondary"
          size="sm"
          icon={RefreshCw}
          onClick={() => void refresh()}
          disabled={isFetching}
          aria-label="Refresh phone numbers"
        >
          Refresh
        </Button>
      </div>
      {softError && (
        <p className="text-xs text-[var(--color-error)]">{softError}</p>
      )}
    </div>
  );
}
