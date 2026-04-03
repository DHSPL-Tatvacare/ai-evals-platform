import { useMemo, useCallback, useRef, useState } from 'react';

import { CredentialPoolManageOverlay, type CredentialPoolManageView } from './CredentialPoolManageOverlay';
import { CredentialPoolEditor } from './CredentialPoolEditor';
import { createSettingsCredentialGroupStorage } from './settingsCredentialGroupStorage';
import type { CredentialPoolConfig, CredentialPoolEntry } from './types';
import {
  createCredentialPoolEntry,
  dedupeCredentialPoolEntries,
  getResolvedCredentialRows,
  mergeCredentialPoolEntries,
} from './utils';

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
  const [manageOverlayOpen, setManageOverlayOpen] = useState(false);
  const [manageView, setManageView] = useState<CredentialPoolManageView>('groups');
  const [queuedImportFile, setQueuedImportFile] = useState<File | null>(null);
  const uploadInputRef = useRef<HTMLInputElement>(null);
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

  const handleUploadRequested = useCallback(() => {
    uploadInputRef.current?.click();
  }, []);

  const handleUploadSelected = useCallback((file: File | null) => {
    if (!file) {
      return;
    }

    setQueuedImportFile(file);
    setManageView('import');
    setManageOverlayOpen(true);
  }, []);

  const handleTestAll = useCallback(async () => {
    if (!onTestEntry) {
      return;
    }

    for (const entry of entries) {
      await onTestEntry(entry.id);
    }
  }, [entries, onTestEntry]);

  const resolvedRows = getResolvedCredentialRows(entries, config.fields);

  return (
    <div className="space-y-4">
      <input
        ref={uploadInputRef}
        type="file"
        accept=".csv"
        className="hidden"
        onChange={(event) => {
          handleUploadSelected(event.target.files?.[0] ?? null);
          event.target.value = '';
        }}
      />

      <CredentialPoolEditor
        config={config}
        entries={entries}
        onEntriesChange={onEntriesChange}
        onAddEntry={handleAddEntry}
        onUploadCsv={handleUploadRequested}
        onOpenManage={() => {
          setManageView('groups');
          setManageOverlayOpen(true);
        }}
        onTestEntry={onTestEntry}
        onTestAll={onTestEntry ? handleTestAll : undefined}
      />

      <CredentialPoolManageOverlay
        isOpen={manageOverlayOpen}
        activeView={manageView}
        onViewChange={setManageView}
        onClose={() => setManageOverlayOpen(false)}
        config={config}
        storage={storage}
        currentEntries={resolvedRows}
        onReplaceEntries={handleReplaceEntries}
        onMergeEntries={handleMergeEntries}
        onImportEntries={handleImportEntries}
        queuedImportFile={queuedImportFile}
        onQueuedImportFileHandled={() => setQueuedImportFile(null)}
      />
    </div>
  );
}
