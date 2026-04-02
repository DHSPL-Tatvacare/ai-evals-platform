import type { AssetVisibility } from '@/types';
import { settingsRepository } from '@/services/api/settingsApi';

import type {
  CredentialGroupStorageAdapter,
  CredentialPoolGroup,
  CredentialPoolGroupCollection,
  CredentialPoolStorageConfig,
} from './types';

const DEFAULT_VISIBILITY: AssetVisibility = 'private';

function nowIso(): string {
  return new Date().toISOString();
}

function createGroupId(): string {
  return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function normalizeCollection(value: CredentialPoolGroupCollection | undefined): CredentialPoolGroupCollection {
  return {
    version: value?.version ?? 1,
    groups: value?.groups ?? [],
  };
}

export function createSettingsCredentialGroupStorage(
  config: CredentialPoolStorageConfig,
): CredentialGroupStorageAdapter {
  const visibility = config.visibility ?? DEFAULT_VISIBILITY;

  async function readCollection(): Promise<CredentialPoolGroupCollection> {
    const value = await settingsRepository.get<CredentialPoolGroupCollection>(config.appId, config.key);
    return normalizeCollection(value);
  }

  async function writeCollection(collection: CredentialPoolGroupCollection): Promise<void> {
    await settingsRepository.set(config.appId, config.key, collection, { visibility });
  }

  return {
    async listGroups() {
      const collection = await readCollection();
      return [...collection.groups].sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
    },

    async saveGroup(name, entries) {
      const collection = await readCollection();
      const timestamp = nowIso();
      const group: CredentialPoolGroup = {
        id: createGroupId(),
        name: name.trim(),
        entries,
        createdAt: timestamp,
        updatedAt: timestamp,
      };

      await writeCollection({
        ...collection,
        groups: [group, ...collection.groups],
      });

      return group;
    },

    async updateGroup(groupId, entries, nextName) {
      const collection = await readCollection();
      const existing = collection.groups.find((group) => group.id === groupId);
      if (!existing) {
        throw new Error('Credential group not found.');
      }

      const updated: CredentialPoolGroup = {
        ...existing,
        name: nextName?.trim() || existing.name,
        entries,
        updatedAt: nowIso(),
      };

      await writeCollection({
        ...collection,
        groups: collection.groups.map((group) => (group.id === groupId ? updated : group)),
      });

      return updated;
    },

    async deleteGroup(groupId) {
      const collection = await readCollection();
      await writeCollection({
        ...collection,
        groups: collection.groups.filter((group) => group.id !== groupId),
      });
    },
  };
}
