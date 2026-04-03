import { Tabs } from '@/components/ui';
import { SettingsSlideOver } from '@/features/settings/components/SettingsSlideOver';

import { CredentialCsvImport } from './CredentialCsvImport';
import { CredentialGroupLibrary } from './CredentialGroupLibrary';
import type { CredentialGroupStorageAdapter, CredentialPoolConfig, CredentialPoolEntry } from './types';

export type CredentialPoolManageView = 'groups' | 'import';

interface CredentialPoolManageOverlayProps {
  isOpen: boolean;
  activeView: CredentialPoolManageView;
  onViewChange: (view: CredentialPoolManageView) => void;
  onClose: () => void;
  config: CredentialPoolConfig;
  storage: CredentialGroupStorageAdapter;
  currentEntries: Array<Record<string, string>>;
  onReplaceEntries: (entries: Array<Record<string, string>>) => void;
  onMergeEntries: (entries: Array<Record<string, string>>) => void;
  onImportEntries: (entries: CredentialPoolEntry[]) => void;
  queuedImportFile: File | null;
  onQueuedImportFileHandled: () => void;
}

export function CredentialPoolManageOverlay({
  isOpen,
  activeView,
  onViewChange,
  onClose,
  config,
  storage,
  currentEntries,
  onReplaceEntries,
  onMergeEntries,
  onImportEntries,
  queuedImportFile,
  onQueuedImportFileHandled,
}: CredentialPoolManageOverlayProps) {
  return (
    <SettingsSlideOver
      isOpen={isOpen}
      onClose={onClose}
      title="Manage Credential Pool"
      description="Use this secondary panel for reusable groups and bulk CSV imports, then return to the active execution rows."
      widthClassName="w-[56vw] max-w-[860px]"
      footerContent={(
        <div className="text-[12px] text-[var(--text-muted)]">
          Changes apply to this run immediately. Close the panel when the active pool looks right.
        </div>
      )}
    >
      <Tabs
        defaultTab={activeView}
        onChange={(tabId) => onViewChange(tabId as CredentialPoolManageView)}
        tabs={[
          {
            id: 'groups',
            label: 'Saved Groups',
            content: (
              <CredentialGroupLibrary
                storage={storage}
                currentEntries={currentEntries}
                onReplaceEntries={onReplaceEntries}
                onMergeEntries={onMergeEntries}
                variant="flat"
                showHeader={false}
              />
            ),
          },
          {
            id: 'import',
            label: 'Import CSV',
            content: (
              <CredentialCsvImport
                config={config}
                onImportEntries={onImportEntries}
                variant="flat"
                showHeader={false}
                queuedFile={queuedImportFile}
                onQueuedFileHandled={onQueuedImportFileHandled}
              />
            ),
          },
        ]}
      />
    </SettingsSlideOver>
  );
}
