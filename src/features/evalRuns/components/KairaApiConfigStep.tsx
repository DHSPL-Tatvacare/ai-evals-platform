import { useCallback, type Dispatch, type SetStateAction } from 'react';

import { Input } from '@/components/ui';
import { CredentialPoolManager } from '@/features/credentialPool/CredentialPoolManager';
import { kairaCredentialPoolConfig } from '@/features/credentialPool/kairaCredentialPoolConfig';
import type { CredentialPoolEntry } from '@/features/credentialPool/types';

interface KairaApiConfigStepProps {
  kairaApiUrl: string;
  kairaTimeout: number;
  credentialEntries: CredentialPoolEntry[];
  onApiUrlChange: (url: string) => void;
  onTimeoutChange: (timeout: number) => void;
  onCredentialEntriesChange: Dispatch<SetStateAction<CredentialPoolEntry[]>>;
}

export function KairaApiConfigStep({
  kairaApiUrl,
  kairaTimeout,
  credentialEntries,
  onApiUrlChange,
  onTimeoutChange,
  onCredentialEntriesChange,
}: KairaApiConfigStepProps) {
  const handleTestEntry = useCallback(async (entryId: string) => {
    const entry = credentialEntries.find((item) => item.id === entryId);
    if (!entry) {
      return;
    }

    const updateEntry = (testStatus: CredentialPoolEntry['testStatus'], testMessage: string | null) => {
      onCredentialEntriesChange((currentEntries) => (
        currentEntries.map((item) => (
          item.id === entryId
            ? { ...item, testStatus, testMessage }
            : item
        ))
      ));
    };

    if (!kairaApiUrl.trim()) {
      updateEntry('error', 'API URL is required');
      return;
    }

    if (!entry.values.userId?.trim()) {
      updateEntry('error', 'User ID is required');
      return;
    }

    if (!entry.values.authToken?.trim()) {
      updateEntry('error', 'Auth token is required');
      return;
    }

    updateEntry('testing', 'Testing...');

    try {
      const response = await fetch(`${kairaApiUrl.replace(/\/$/, '')}/health`, {
        method: 'GET',
        headers: { Authorization: `Bearer ${entry.values.authToken.trim()}` },
        signal: AbortSignal.timeout(10000),
      });

      if (!response.ok) {
        updateEntry('error', `HTTP ${response.status}: ${response.statusText}`);
        return;
      }

      updateEntry('success', 'Connected');
    } catch (error) {
      updateEntry('error', error instanceof Error ? error.message : 'Connection failed');
    }
  }, [credentialEntries, kairaApiUrl, onCredentialEntriesChange]);

  return (
    <div className="space-y-5">
      <div>
        <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-1.5">
          Kaira API URL <span className="text-[var(--color-error)]">*</span>
        </label>
        <Input
          value={kairaApiUrl}
          onChange={(e) => onApiUrlChange(e.target.value)}
          placeholder="https://kaira-api.example.com"
        />
      </div>

      <div>
        <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-1.5">
          Request Timeout (seconds)
        </label>
        <Input
          type="number"
          value={kairaTimeout}
          onChange={(e) => onTimeoutChange(Math.max(30, Math.min(300, Number(e.target.value) || 120)))}
          min={30}
          max={300}
        />
        <p className="mt-1 text-[11px] text-[var(--text-muted)]">
          Max time to wait for each Kaira API response. Increase if you see frequent timeouts.
        </p>
      </div>

      <CredentialPoolManager
        config={kairaCredentialPoolConfig}
        entries={credentialEntries}
        onEntriesChange={onCredentialEntriesChange}
        onTestEntry={handleTestEntry}
      />
    </div>
  );
}
