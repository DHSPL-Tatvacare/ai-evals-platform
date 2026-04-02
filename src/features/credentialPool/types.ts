import type { AssetVisibility } from '@/types';
import type { CsvFieldDef } from '@/features/csvImport/types';

export interface CredentialPoolFieldConfig {
  key: string;
  label: string;
  placeholder?: string;
  description?: string;
  required?: boolean;
  secret?: boolean;
}

export type CredentialPoolEntrySource = 'seed' | 'manual' | 'csv' | 'group';
export type CredentialTestStatus = 'idle' | 'testing' | 'success' | 'error';

export interface CredentialPoolEntry {
  id: string;
  values: Record<string, string>;
  source: CredentialPoolEntrySource;
  testStatus: CredentialTestStatus;
  testMessage: string | null;
}

export interface CredentialPoolGroup {
  id: string;
  name: string;
  entries: Array<Record<string, string>>;
  createdAt: string;
  updatedAt: string;
}

export interface CredentialPoolGroupCollection {
  version: number;
  groups: CredentialPoolGroup[];
}

export interface CredentialPoolStorageConfig {
  appId: string | null;
  key: string;
  visibility?: AssetVisibility;
}

export interface CredentialPoolConfig {
  title: string;
  description?: string;
  fields: CredentialPoolFieldConfig[];
  csvSchema: CsvFieldDef[];
  dedupeKeys: string[];
  storage: CredentialPoolStorageConfig;
  primaryFieldKey: string;
  redactedFieldKeys?: string[];
}

export interface CredentialGroupStorageAdapter {
  listGroups: () => Promise<CredentialPoolGroup[]>;
  saveGroup: (name: string, entries: Array<Record<string, string>>) => Promise<CredentialPoolGroup>;
  updateGroup: (groupId: string, entries: Array<Record<string, string>>, nextName?: string) => Promise<CredentialPoolGroup>;
  deleteGroup: (groupId: string) => Promise<void>;
}
