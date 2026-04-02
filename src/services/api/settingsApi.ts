/**
 * Settings API - HTTP client for settings API.
 *
 * Backend returns camelCase via Pydantic alias_generator.
 * Query params remain snake_case (FastAPI query params).
 *
 * Default reads return resolved winners by key. Management views can request
 * the full visible set with include_all=true.
 */
import type { AssetVisibility, SettingRecord } from '@/types';
import { apiRequest } from './client';

interface ApiSettingRecord<TValue = unknown> {
  id: number;
  appId: string | null;
  key: string;
  value: TValue;
  visibility: AssetVisibility;
  forkedFrom?: number | null;
  updatedAt: string;
  userId: string;
  sharedBy?: string | null;
  sharedAt?: string | null;
}

export interface SettingListOptions {
  key?: string;
  includeAll?: boolean;
}

export interface SettingWriteOptions {
  visibility?: AssetVisibility;
  forkedFrom?: number | null;
}

function toSettingRecord<TValue>(record: ApiSettingRecord<TValue>): SettingRecord<TValue> {
  return {
    id: record.id,
    appId: record.appId,
    key: record.key,
    value: record.value,
    visibility: record.visibility,
    forkedFrom: record.forkedFrom,
    updatedAt: new Date(record.updatedAt),
    userId: record.userId,
    sharedBy: record.sharedBy,
    sharedAt: record.sharedAt ? new Date(record.sharedAt) : null,
  };
}

export const settingsRepository = {
  async list<TValue = unknown>(
    appId: string | null,
    options: SettingListOptions = {},
  ): Promise<SettingRecord<TValue>[]> {
    const params = new URLSearchParams();
    params.set('app_id', appId ?? '');
    if (options.key) {
      params.set('key', options.key);
    }
    if (options.includeAll) {
      params.set('include_all', 'true');
    }

    const data = await apiRequest<ApiSettingRecord<TValue>[]>(`/api/settings?${params.toString()}`);
    return data.map(toSettingRecord);
  },

  async getRecord<TValue = unknown>(
    appId: string | null,
    key: string,
    options: Omit<SettingListOptions, 'key'> = {},
  ): Promise<SettingRecord<TValue> | undefined> {
    const records = await this.list<TValue>(appId, { ...options, key });
    return records[0];
  },

  async get<TValue = unknown>(
    appId: string | null,
    key: string,
    options: Omit<SettingListOptions, 'key'> = {},
  ): Promise<TValue | undefined> {
    try {
      const record = await this.getRecord<TValue>(appId, key, options);
      return record?.value;
    } catch {
      return undefined;
    }
  },

  async set<TValue>(
    appId: string | null,
    key: string,
    value: TValue,
    options: SettingWriteOptions = {},
  ): Promise<SettingRecord<TValue>> {
    const data = await apiRequest<ApiSettingRecord<TValue>>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify({
        appId: appId ?? '',
        key,
        value,
        visibility: options.visibility ?? 'private',
        forkedFrom: options.forkedFrom ?? null,
      }),
    });
    return toSettingRecord(data);
  },

  async delete(appId: string | null, key: string): Promise<void> {
    const params = new URLSearchParams({ key });
    params.set('app_id', appId ?? '');

    await apiRequest(`/api/settings?${params.toString()}`, {
      method: 'DELETE',
    });
  },
};
