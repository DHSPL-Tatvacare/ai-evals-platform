import { useCallback, useEffect, useState } from 'react';

import { Combobox, type ComboboxOption } from '@/components/ui/Combobox';
import { Input } from '@/components/ui/Input';
import { useProviderPhoneNumbers } from '@/features/orchestration/queries/referenceData';
import {
  getConnection,
  type ProviderPhoneNumberSummary,
} from '@/services/api/orchestrationConnections';

interface Props {
  /** WATI connection UUID. Picker is disabled until a connection is selected. */
  connectionId?: string;
  value: string;
  onChange(next: string): void;
}

/** WATI channel-number picker.
 *  Primary source: live provider endpoint; falls back to stored channel_numbers; then free-text. */
export function WatiChannelPicker({ connectionId, value, onChange }: Props) {
  const { data, isFetching } = useProviderPhoneNumbers(connectionId);
  const [storedChannels, setStoredChannels] = useState<string[]>([]);
  const [loadingStored, setLoadingStored] = useState(false);

  const liveItems: ProviderPhoneNumberSummary[] = data?.items ?? [];
  const hasLive = liveItems.length > 0;

  // Fetch stored channel_numbers only when the live list comes back empty and there's a connection.
  const fetchStored = useCallback(async () => {
    if (!connectionId || isFetching || hasLive) return;
    setLoadingStored(true);
    try {
      const conn = await getConnection(connectionId);
      const raw = conn.configRedacted.channel_numbers;
      const arr = Array.isArray(raw)
        ? raw.filter((s): s is string => typeof s === 'string' && s.length > 0)
        : [];
      setStoredChannels(arr);
    } catch {
      setStoredChannels([]);
    } finally {
      setLoadingStored(false);
    }
  }, [connectionId, isFetching, hasLive]);

  useEffect(() => {
    // Reset stored channels whenever the live data changes.
    if (hasLive) {
      setStoredChannels([]);
      return;
    }
    // Only load stored when live is settled (not fetching) and empty.
    if (!isFetching && !hasLive) {
      void fetchStored();
    }
  }, [connectionId, hasLive, isFetching, fetchStored]);

  if (!connectionId) {
    return (
      <p className="text-xs text-[var(--text-secondary)]">
        Pick a WATI connection above to load channel numbers.
      </p>
    );
  }

  const loading = isFetching || loadingStored;

  // Build option list from whichever source has data.
  const rawNumbers = hasLive
    ? liveItems.map((i) => i.phoneNumber)
    : storedChannels;

  // Keep an already-saved value selectable even when absent from the list.
  const allNumbers = Array.from(new Set([...(value ? [value] : []), ...rawNumbers]));

  const options: ComboboxOption[] = allNumbers.map((num) => {
    const match = hasLive ? liveItems.find((i) => i.phoneNumber === num) : undefined;
    return {
      value: num,
      label: match?.label ? `${num} · ${match.label}` : num,
    };
  });

  if (!loading && options.length === 0) {
    return (
      <div className="flex flex-col gap-1">
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="+911234567890"
        />
      </div>
    );
  }

  return (
    <Combobox
      options={options}
      value={value}
      onChange={onChange}
      placeholder={loading ? 'Loading channels…' : 'Select a channel number'}
      disabled={loading && options.length === 0}
      loading={loading}
    />
  );
}
