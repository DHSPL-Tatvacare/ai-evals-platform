import { useMemo, useCallback } from 'react';

import { createSettingsCredentialGroupStorage } from './settingsCredentialGroupStorage';
import type { CredentialPoolConfig, CredentialPoolEntry } from './types';
import {
  buildCredentialPoolReviewSummary,
  createCredentialPoolEntry,
  dedupeCredentialPoolEntries,
  getResolvedCredentialRows,
  mergeCredentialPoolEntries,
} from './utils';
import { CredentialCsvImport } from './CredentialCsvImport';
import { CredentialGroupLibrary } from './CredentialGroupLibrary';
import { CredentialPoolEditor } from './CredentialPoolEditor';

interface CredentialPoolManagerProps {
  config: CredentialPoolConfig;
  entries: CredentialPoolEntry[];
  onEntriesChange: (entries: CredentialPoolEntry[]) => void;
  onTestEntry?: (entryId: string) => Promise<void>;
}

export function CredentialPoolManager({
  config,
  entries,
  onEntriesChange,
  onTestEntry,
}: CredentialPoolManagerProps) {
  const storage = useMemo(
    () => createSettingsCredentialGroupStorage(config.storage),
    [config.storage],
  );

  const handleAddEntry = useCallback(() => {
    onEntriesChange([
      ...entries,
      createCredentialPoolEntry(
        Object.fromEntries(config.fields.map((field) => [field.key, ''])),
        'manual',
      ),
    ]);
  }, [config.fields, entries, onEntriesChange]);

  const handleReplaceEntries = useCallback((nextEntries: Array<Record<string, string>>) => {
    onEntriesChange(
      dedupeCredentialPoolEntries(
        nextEntries.map((entry) => createCredentialPoolEntry(entry, 'group')),
        config.dedupeKeys,
      ),
    );
  }, [config.dedupeKeys, onEntriesChange]);

  const handleMergeEntries = useCallback((nextEntries: Array<Record<string, string>>) => {
    onEntriesChange(
      mergeCredentialPoolEntries(
        entries,
        nextEntries.map((entry) => createCredentialPoolEntry(entry, 'group')),
        config.dedupeKeys,
      ),
    );
  }, [config.dedupeKeys, entries, onEntriesChange]);

  const handleImportEntries = useCallback((importedEntries: CredentialPoolEntry[]) => {
    onEntriesChange(mergeCredentialPoolEntries(entries, importedEntries, config.dedupeKeys));
  }, [config.dedupeKeys, entries, onEntriesChange]);

  const handleTestAll = useCallback(async () => {
    if (!onTestEntry) {
      return;
    }

    for (const entry of entries) {
      await onTestEntry(entry.id);
    }
  }, [entries, onTestEntry]);

  const summary = buildCredentialPoolReviewSummary(entries, config);
  const resolvedRows = getResolvedCredentialRows(entries, config.fields);

  return (
    <div className="space-y-4">
      <div className="rounded-[6px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2.5">
        <p className="text-[12px] font-medium text-[var(--text-primary)]">
          {summary.readyCount} ready credential row{summary.readyCount === 1 ? '' : 's'}
        </p>
        <p className="text-[11px] text-[var(--text-muted)]">
          Parallel execution can only use one active case per resolved {config.fields.find((field) => field.key === config.primaryFieldKey)?.label ?? 'identity'}.
        </p>
        {resolvedRows.length > 0 && (
          <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
            Active identities: {summary.primaryValues.join(', ')}
          </p>
        )}
      </div>

      <CredentialGroupLibrary
        storage={storage}
        currentEntries={resolvedRows}
        onReplaceEntries={handleReplaceEntries}
        onMergeEntries={handleMergeEntries}
      />

      <CredentialCsvImport config={config} onImportEntries={handleImportEntries} />

      <CredentialPoolEditor
        config={config}
        entries={entries}
        onEntriesChange={onEntriesChange}
        onAddEntry={handleAddEntry}
        onTestEntry={onTestEntry}
        onTestAll={onTestEntry ? handleTestAll : undefined}
      />
    </div>
  );
}
