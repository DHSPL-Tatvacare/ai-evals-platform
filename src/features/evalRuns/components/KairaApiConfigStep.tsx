import { useCallback, type Dispatch, type SetStateAction } from 'react';

import { Input } from '@/components/ui';
import { CredentialPoolManager } from '@/features/credentialPool/CredentialPoolManager';
import { kairaCredentialPoolConfig } from '@/features/credentialPool/kairaCredentialPoolConfig';
import type { CredentialPoolEntry } from '@/features/credentialPool/types';
import { WizardSection, WizardStepLayout } from './WizardStepLayout';

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
    <WizardStepLayout
      eyebrow="Kaira Access"
      title="Connect the target environment"
      description="Point the run at the right Kaira endpoint, then choose the user identities you want the stress test to exercise."
    >
      <WizardSection title="Connection" description="These settings apply to every case in the run.">
        <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_220px]">
          <div>
            <label className="mb-1.5 block text-[13px] font-medium text-[var(--text-primary)]">
              Kaira API URL <span className="text-[var(--color-error)]">*</span>
            </label>
            <Input
              value={kairaApiUrl}
              onChange={(e) => onApiUrlChange(e.target.value)}
              placeholder="https://kaira-api.example.com"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-[13px] font-medium text-[var(--text-primary)]">
              Request Timeout (seconds)
            </label>
            <Input
              type="number"
              value={kairaTimeout}
              onChange={(e) => onTimeoutChange(Math.max(30, Math.min(300, Number(e.target.value) || 120)))}
              min={30}
              max={300}
            />
            <p className="mt-1.5 text-[12px] text-[var(--text-muted)]">
              Max time to wait for each Kaira API response.
            </p>
          </div>
        </div>
      </WizardSection>

      <WizardSection
        title={kairaCredentialPoolConfig.title}
        description="Keep the entry editor inline, and use upload or saved groups only when you need bulk workflows."
      >
        <CredentialPoolManager
          config={kairaCredentialPoolConfig}
          entries={credentialEntries}
          onEntriesChange={onCredentialEntriesChange}
          onTestEntry={handleTestEntry}
        />
      </WizardSection>
    </WizardStepLayout>
  );
}
