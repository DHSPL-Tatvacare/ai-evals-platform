/**
 * Evaluators API - HTTP client for evaluators API.
 *
 * Backend returns camelCase via Pydantic alias_generator.
 * Query params remain snake_case (FastAPI query params).
 */
import type {
  EvaluatorDefinition,
  EvaluatorVisibilityFilter,
  PromptValidation,
  VariableInfo,
} from '@/types';
import { normalizeAssetVisibility } from '@/types/settings.types';
import type { AssetVisibility, LegacyAssetVisibility } from '@/types/settings.types';
import { apiRequest } from './client';

/** Shape returned by backend (camelCase, dates as strings) */
interface ApiEvaluator {
  id: string;
  userId?: string;
  tenantId?: string;
  ownerId?: string;
  ownerName?: string;
  appId: string;
  listingId: string | null;
  name: string;
  prompt: string;
  modelId: string;
  outputSchema: unknown;
  visibility: LegacyAssetVisibility;
  linkedRuleIds?: string[];
  sharedBy?: string | null;
  sharedAt?: string | null;
  forkedFrom?: string;
  createdAt: string;
  updatedAt: string;
}

export interface EvaluatorListOptions {
  listingId?: string;
  filter?: EvaluatorVisibilityFilter;
}

function normalizeVisibilityFilter(filter: EvaluatorVisibilityFilter = 'all'): string | undefined {
  return filter === 'all' ? undefined : filter;
}

function toEvaluatorDefinition(e: ApiEvaluator): EvaluatorDefinition {
  return {
    id: e.id,
    userId: e.userId,
    tenantId: e.tenantId,
    ownerId: e.ownerId,
    ownerName: e.ownerName,
    appId: e.appId,
    listingId: e.listingId ?? undefined,
    name: e.name,
    prompt: e.prompt,
    modelId: e.modelId,
    outputSchema: e.outputSchema as EvaluatorDefinition['outputSchema'],
    visibility: normalizeAssetVisibility(e.visibility),
    forkedFrom: e.forkedFrom,
    sharedBy: e.sharedBy,
    sharedAt: e.sharedAt,
    linkedRuleIds: e.linkedRuleIds ?? [],
    createdAt: new Date(e.createdAt),
    updatedAt: new Date(e.updatedAt),
  };
}

export function filterEvaluatorsByVisibility(
  evaluators: EvaluatorDefinition[],
  filter: EvaluatorVisibilityFilter = 'all',
): EvaluatorDefinition[] {
  if (filter === 'all') {
    return evaluators;
  }
  if (filter === 'private') {
    return evaluators.filter((evaluator) => (evaluator.visibility ?? 'private') === 'private');
  }
  if (filter === 'shared') {
    return evaluators.filter((evaluator) => (evaluator.visibility ?? 'private') === 'shared');
  }
  return evaluators;
}

export const evaluatorsRepository = {
  async save(evaluator: EvaluatorDefinition): Promise<EvaluatorDefinition> {
    const body = {
      name: evaluator.name,
      prompt: evaluator.prompt,
      modelId: evaluator.modelId,
      outputSchema: evaluator.outputSchema,
      visibility: evaluator.visibility,
      linkedRuleIds: evaluator.linkedRuleIds ?? [],
      forkedFrom: evaluator.forkedFrom ?? null,
      listingId: evaluator.listingId ?? null,
      appId: evaluator.appId,
    };

    if (evaluator.id) {
      const data = await apiRequest<ApiEvaluator>(`/api/evaluators/${evaluator.id}`, {
        method: 'PUT',
        body: JSON.stringify(body),
      });
      return toEvaluatorDefinition(data);
    }

    const data = await apiRequest<ApiEvaluator>('/api/evaluators', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    return toEvaluatorDefinition(data);
  },

  async getById(id: string): Promise<EvaluatorDefinition | undefined> {
    try {
      const data = await apiRequest<ApiEvaluator>(`/api/evaluators/${id}`);
      return toEvaluatorDefinition(data);
    } catch {
      return undefined;
    }
  },

  async list(appId: string, opts: EvaluatorListOptions = {}): Promise<EvaluatorDefinition[]> {
    const params = new URLSearchParams({ app_id: appId });
    const filter = normalizeVisibilityFilter(opts.filter);
    if (opts.listingId) {
      params.set('listing_id', opts.listingId);
    }
    if (filter) {
      params.set('filter', filter);
    }
    const data = await apiRequest<ApiEvaluator[]>(`/api/evaluators?${params.toString()}`);
    return data.map(toEvaluatorDefinition);
  },

  async getByAppId(appId: string): Promise<EvaluatorDefinition[]> {
    return this.list(appId);
  },

  async getForListing(appId: string, listingId: string): Promise<EvaluatorDefinition[]> {
    return this.list(appId, { listingId });
  },

  async getPrivate(appId: string): Promise<EvaluatorDefinition[]> {
    return this.list(appId, { filter: 'private' });
  },

  async getShared(appId: string): Promise<EvaluatorDefinition[]> {
    return this.list(appId, { filter: 'shared' });
  },

  async fork(sourceId: string, targetListingId?: string): Promise<EvaluatorDefinition> {
    const params = targetListingId ? `?listing_id=${targetListingId}` : '';
    const data = await apiRequest<ApiEvaluator>(
      `/api/evaluators/${sourceId}/fork${params}`,
      { method: 'POST' }
    );
    return toEvaluatorDefinition(data);
  },

  async setVisibility(id: string, visibility: AssetVisibility): Promise<EvaluatorDefinition> {
    const data = await apiRequest<ApiEvaluator>(`/api/evaluators/${id}/visibility`, {
      method: 'PATCH',
      body: JSON.stringify({ visibility }),
    });
    return toEvaluatorDefinition(data);
  },

  async delete(id: string): Promise<void> {
    await apiRequest(`/api/evaluators/${id}`, {
      method: 'DELETE',
    });
  },

  /** Fetch available template variables for an app (backend variable registry). */
  async getVariables(appId: string, sourceType?: string): Promise<VariableInfo[]> {
    const params = new URLSearchParams({ appId });
    if (sourceType) params.set('sourceType', sourceType);
    return apiRequest<VariableInfo[]>(`/api/evaluators/variables?${params}`);
  },

  /** Validate a prompt's template variables against the backend registry. */
  async validatePrompt(prompt: string, appId: string, sourceType?: string): Promise<PromptValidation> {
    const params = new URLSearchParams({ appId });
    if (sourceType) params.set('sourceType', sourceType);
    return apiRequest<PromptValidation>(`/api/evaluators/validate-prompt?${params}`, {
      method: 'POST',
      body: JSON.stringify({ prompt }),
    });
  },

  /** Create recommended seed evaluators for a voice-rx listing. */
  async seedDefaults(listingId: string): Promise<EvaluatorDefinition[]> {
    const data = await apiRequest<ApiEvaluator[]>(
      `/api/evaluators/seed-defaults?appId=voice-rx&listingId=${listingId}`,
      { method: 'POST' },
    );
    return data.map(toEvaluatorDefinition);
  },

  /** Create recommended seed evaluators for an app (app-level, no listing). */
  async seedAppDefaults(appId: string): Promise<EvaluatorDefinition[]> {
    const data = await apiRequest<ApiEvaluator[]>(
      `/api/evaluators/seed-defaults?appId=${appId}`,
      { method: 'POST' },
    );
    return data.map(toEvaluatorDefinition);
  },

  /** Extract available API response variable paths for a listing. */
  async getApiPaths(listingId: string): Promise<string[]> {
    return apiRequest<string[]>(`/api/evaluators/variables/api-paths?listingId=${listingId}`);
  },
};
