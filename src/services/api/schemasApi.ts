/**
 * Schemas API - HTTP client for schemas API.
 *
 * Backend returns camelCase via Pydantic alias_generator.
 * Query params remain snake_case (FastAPI query params).
 *
 * Note: Backend field is `schemaData` but frontend type uses `schema`.
 * We map schemaData -> schema on reads and schema -> schemaData on writes.
 */
import type { SchemaDefinition, AppId } from '@/types';
import { normalizeAssetVisibility } from '@/types/settings.types';
import type { AssetVisibility, LegacyAssetVisibility } from '@/types/settings.types';
import { apiRequest } from './client';

/** Shape returned by backend (camelCase, dates as strings) */
interface ApiSchema {
  id: number;
  userId?: string;
  tenantId?: string;
  appId: string;
  promptType: string;
  version: number;
  branchKey: string;
  forkedFrom: number | null;
  sharedBy: string | null;
  sharedAt: string | null;
  name: string;
  schemaData: Record<string, unknown>;
  description?: string;
  isDefault?: boolean;
  sourceType?: string | null;
  visibility: LegacyAssetVisibility;
  createdAt: string;
  updatedAt: string;
}

export interface SchemaListOptions {
  promptType?: SchemaDefinition['promptType'];
  sourceType?: SchemaDefinition['sourceType'];
  branchKey?: string;
  latestOnly?: boolean;
  visibility?: AssetVisibility;
}

function toSchemaDefinition(s: ApiSchema): SchemaDefinition {
  return {
    id: String(s.id),
    userId: s.userId,
    tenantId: s.tenantId,
    name: s.name,
    version: s.version,
    branchKey: s.branchKey,
    visibility: normalizeAssetVisibility(s.visibility),
    forkedFrom: s.forkedFrom,
    sharedBy: s.sharedBy,
    sharedAt: s.sharedAt,
    promptType: s.promptType as SchemaDefinition['promptType'],
    schema: s.schemaData,
    description: s.description,
    isDefault: s.isDefault,
    sourceType: (s.sourceType as SchemaDefinition['sourceType']) ?? null,
    createdAt: new Date(s.createdAt),
    updatedAt: new Date(s.updatedAt),
  };
}

export function filterSchemasByVisibility(
  schemas: SchemaDefinition[],
  visibility?: AssetVisibility,
): SchemaDefinition[] {
  if (!visibility) {
    return schemas;
  }
  return schemas.filter((schema) => schema.visibility === visibility);
}

export const schemasRepository = {
  async getAll(
    appId: AppId,
    promptType?: SchemaDefinition['promptType'],
    opts: SchemaListOptions = {},
  ): Promise<SchemaDefinition[]> {
    const params = new URLSearchParams({ app_id: appId });
    const effectivePromptType = promptType ?? opts.promptType;
    if (effectivePromptType) {
      params.append('prompt_type', effectivePromptType);
    }
    if (opts.sourceType) {
      params.append('source_type', opts.sourceType);
    }
    if (opts.branchKey) {
      params.append('branch_key', opts.branchKey);
    }
    if (opts.latestOnly !== undefined) {
      params.append('latest_only', String(opts.latestOnly));
    }
    const data = await apiRequest<ApiSchema[]>(`/api/schemas?${params}`);
    const schemas = data.map(toSchemaDefinition);
    return filterSchemasByVisibility(schemas, opts.visibility);
  },

  async getById(_appId: AppId, id: string): Promise<SchemaDefinition | null> {
    try {
      const data = await apiRequest<ApiSchema>(`/api/schemas/${id}`);
      return toSchemaDefinition(data);
    } catch {
      return null;
    }
  },

  async getLatestVersion(appId: AppId, promptType: SchemaDefinition['promptType']): Promise<number> {
    const schemas = await this.getAll(appId, promptType);
    if (schemas.length === 0) return 0;
    return Math.max(...schemas.map(s => s.version));
  },

  async getVersionHistory(
    appId: AppId,
    branchKey: string,
    opts: Omit<SchemaListOptions, 'branchKey' | 'latestOnly'> = {},
  ): Promise<SchemaDefinition[]> {
    return this.getAll(appId, opts.promptType, {
      ...opts,
      branchKey,
      latestOnly: false,
    });
  },

  async save(appId: AppId, schema: SchemaDefinition): Promise<SchemaDefinition> {
    const data = await apiRequest<ApiSchema>('/api/schemas', {
      method: 'POST',
      body: JSON.stringify({
        appId: appId,
        promptType: schema.promptType,
        branchKey: schema.branchKey ?? null,
        schemaData: schema.schema,
        description: schema.description,
        isDefault: schema.isDefault,
        sourceType: schema.sourceType ?? null,
        name: schema.name,
        visibility: schema.visibility ?? 'private',
        forkedFrom: schema.forkedFrom ?? null,
      }),
    });
    return toSchemaDefinition(data);
  },

  async updateMetadata(
    schemaId: string,
    updates: Pick<SchemaDefinition, 'name' | 'description'>,
  ): Promise<SchemaDefinition> {
    const data = await apiRequest<ApiSchema>(`/api/schemas/${schemaId}`, {
      method: 'PUT',
      body: JSON.stringify({
        name: updates.name,
        description: updates.description,
      }),
    });
    return toSchemaDefinition(data);
  },

  async checkDependencies(_appId: AppId, _id: string): Promise<{ count: number; listings: string[] }> {
    // TODO: implement server-side dependency check when needed
    void _appId;
    void _id;
    return { count: 0, listings: [] };
  },

  async delete(_appId: AppId, id: string): Promise<void> {
    await apiRequest(`/api/schemas/${id}`, {
      method: 'DELETE',
    });
  },

  async syncFromListing(listingId: string): Promise<{ synced: boolean; field_count: number }> {
    return apiRequest('/api/schemas/sync-from-listing', {
      method: 'POST',
      body: JSON.stringify({ listing_id: listingId }),
    });
  },

  async fork(schemaId: string): Promise<SchemaDefinition> {
    const data = await apiRequest<ApiSchema>(`/api/schemas/${schemaId}/fork`, {
      method: 'POST',
    });
    return toSchemaDefinition(data);
  },

  async patchVisibility(schemaId: string, visibility: AssetVisibility): Promise<SchemaDefinition> {
    const data = await apiRequest<ApiSchema>(`/api/schemas/${schemaId}/visibility`, {
      method: 'PATCH',
      body: JSON.stringify({ visibility }),
    });
    return toSchemaDefinition(data);
  },
};
