/**
 * Prompts API - HTTP client for prompts API.
 *
 * Backend returns camelCase via Pydantic alias_generator.
 * Query params remain snake_case (FastAPI query params).
 */
import type { PromptDefinition, AppId } from '@/types';
import { normalizeAssetVisibility } from '@/types/settings.types';
import type { AssetVisibility, LegacyAssetVisibility } from '@/types/settings.types';
import { apiRequest } from './client';

/** Shape returned by backend (camelCase, dates as strings) */
interface ApiPrompt {
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
  prompt: string;
  description?: string;
  isDefault?: boolean;
  sourceType?: string | null;
  visibility: LegacyAssetVisibility;
  createdAt: string;
  updatedAt: string;
}

export interface PromptListOptions {
  promptType?: PromptDefinition['promptType'];
  sourceType?: PromptDefinition['sourceType'];
  branchKey?: string;
  latestOnly?: boolean;
  visibility?: AssetVisibility;
}

function toPromptDefinition(p: ApiPrompt): PromptDefinition {
  return {
    id: String(p.id),
    userId: p.userId,
    tenantId: p.tenantId,
    name: p.name,
    version: p.version,
    branchKey: p.branchKey,
    visibility: normalizeAssetVisibility(p.visibility),
    forkedFrom: p.forkedFrom,
    sharedBy: p.sharedBy,
    sharedAt: p.sharedAt,
    promptType: p.promptType as PromptDefinition['promptType'],
    prompt: p.prompt,
    description: p.description,
    isDefault: p.isDefault,
    sourceType: (p.sourceType as PromptDefinition['sourceType']) ?? null,
    createdAt: new Date(p.createdAt),
    updatedAt: new Date(p.updatedAt),
  };
}

export function filterPromptsByVisibility(
  prompts: PromptDefinition[],
  visibility?: AssetVisibility,
): PromptDefinition[] {
  if (!visibility) {
    return prompts;
  }
  return prompts.filter((prompt) => prompt.visibility === visibility);
}

export const promptsRepository = {
  async getAll(
    appId: AppId,
    promptType?: PromptDefinition['promptType'],
    opts: PromptListOptions = {},
  ): Promise<PromptDefinition[]> {
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
    const data = await apiRequest<ApiPrompt[]>(`/api/prompts?${params}`);
    const prompts = data.map(toPromptDefinition);
    return filterPromptsByVisibility(prompts, opts.visibility);
  },

  async getById(_appId: AppId, id: string): Promise<PromptDefinition | null> {
    try {
      const data = await apiRequest<ApiPrompt>(`/api/prompts/${id}`);
      return toPromptDefinition(data);
    } catch {
      return null;
    }
  },

  async getLatestVersion(appId: AppId, promptType: PromptDefinition['promptType']): Promise<number> {
    const prompts = await this.getAll(appId, promptType);
    if (prompts.length === 0) return 0;
    return Math.max(...prompts.map(p => p.version));
  },

  async getVersionHistory(
    appId: AppId,
    branchKey: string,
    opts: Omit<PromptListOptions, 'branchKey' | 'latestOnly'> = {},
  ): Promise<PromptDefinition[]> {
    return this.getAll(appId, opts.promptType, {
      ...opts,
      branchKey,
      latestOnly: false,
    });
  },

  async save(appId: AppId, prompt: PromptDefinition): Promise<PromptDefinition> {
    const data = await apiRequest<ApiPrompt>('/api/prompts', {
      method: 'POST',
      body: JSON.stringify({
        appId: appId,
        promptType: prompt.promptType,
        branchKey: prompt.branchKey ?? null,
        prompt: prompt.prompt,
        description: prompt.description,
        isDefault: prompt.isDefault,
        sourceType: prompt.sourceType,
        name: prompt.name,
        visibility: prompt.visibility ?? 'private',
        forkedFrom: prompt.forkedFrom ?? null,
      }),
    });
    return toPromptDefinition(data);
  },

  async updateMetadata(
    promptId: string,
    updates: Pick<PromptDefinition, 'name' | 'description'>,
  ): Promise<PromptDefinition> {
    const data = await apiRequest<ApiPrompt>(`/api/prompts/${promptId}`, {
      method: 'PUT',
      body: JSON.stringify({
        name: updates.name,
        description: updates.description,
      }),
    });
    return toPromptDefinition(data);
  },

  async checkDependencies(_appId: AppId, _id: string): Promise<{ count: number; listings: string[] }> {
    // TODO: implement server-side dependency check when needed
    void _appId;
    void _id;
    return { count: 0, listings: [] };
  },

  async delete(_appId: AppId, id: string): Promise<void> {
    await apiRequest(`/api/prompts/${id}`, {
      method: 'DELETE',
    });
  },

  async fork(promptId: string): Promise<PromptDefinition> {
    const data = await apiRequest<ApiPrompt>(`/api/prompts/${promptId}/fork`, {
      method: 'POST',
    });
    return toPromptDefinition(data);
  },

  async patchVisibility(promptId: string, visibility: AssetVisibility): Promise<PromptDefinition> {
    const data = await apiRequest<ApiPrompt>(`/api/prompts/${promptId}/visibility`, {
      method: 'PATCH',
      body: JSON.stringify({ visibility }),
    });
    return toPromptDefinition(data);
  },

};
