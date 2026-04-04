/**
 * Apps API - HTTP client for registered app metadata and config.
 *
 * Backend returns camelCase via Pydantic alias_generator.
 * Config payloads are merged against local fallbacks so the frontend can
 * keep rendering while app configs are loading or partially seeded.
 */
import { apiRequest } from './client';
import {
  APP_CONFIG_FALLBACKS,
  mergeAppConfig,
  normalizeAssetVisibility,
  type AppConfig,
  type AppId,
  type AppSummary,
} from '@/types';

interface ApiAppSummary {
  id: string;
  slug: string;
  displayName: string;
  description: string;
  iconUrl: string;
  isActive: boolean;
}

type ApiAppConfig = Partial<AppConfig>;

function normalizeOptionalVisibility(
  visibility: 'private' | 'shared' | 'app' | undefined,
  fallback: 'private' | 'shared',
): 'private' | 'shared' {
  return visibility === undefined ? fallback : normalizeAssetVisibility(visibility);
}

function normalizeAppConfig(appId: AppId, config: Record<string, unknown>): Partial<AppConfig> {
  const rawAssetDefaults =
    typeof config.assetDefaults === 'object' && config.assetDefaults !== null
      ? (config.assetDefaults as Record<string, unknown>)
      : {};
  const rawAnalytics =
    typeof config.analytics === 'object' && config.analytics !== null
      ? (config.analytics as Record<string, unknown>)
      : {};
  const rawAnalyticsAssets =
    typeof rawAnalytics.assets === 'object' && rawAnalytics.assets !== null
      ? (rawAnalytics.assets as Record<string, unknown>)
      : {};
  const rawEvaluator =
    typeof config.evaluator === 'object' && config.evaluator !== null
      ? (config.evaluator as Record<string, unknown>)
      : {};

  return {
    ...config,
    evaluator: {
      ...APP_CONFIG_FALLBACKS[appId].evaluator,
      ...(rawEvaluator as Partial<AppConfig['evaluator']>),
      defaultVisibility: normalizeOptionalVisibility(
        rawEvaluator.defaultVisibility as 'private' | 'shared' | 'app' | undefined,
        APP_CONFIG_FALLBACKS[appId].evaluator.defaultVisibility,
      ),
    },
    assetDefaults: {
      ...APP_CONFIG_FALLBACKS[appId].assetDefaults,
      evaluator: normalizeOptionalVisibility(
        rawAssetDefaults.evaluator as 'private' | 'shared' | 'app' | undefined,
        APP_CONFIG_FALLBACKS[appId].assetDefaults.evaluator,
      ),
      prompt: normalizeOptionalVisibility(
        rawAssetDefaults.prompt as 'private' | 'shared' | 'app' | undefined,
        APP_CONFIG_FALLBACKS[appId].assetDefaults.prompt,
      ),
      schema: normalizeOptionalVisibility(
        rawAssetDefaults.schema as 'private' | 'shared' | 'app' | undefined,
        APP_CONFIG_FALLBACKS[appId].assetDefaults.schema,
      ),
      adversarialContract: normalizeOptionalVisibility(
        (rawAssetDefaults.adversarialContract ?? rawAssetDefaults.adversarial_contract) as 'private' | 'shared' | 'app' | undefined,
        APP_CONFIG_FALLBACKS[appId].assetDefaults.adversarialContract,
      ),
      llmSettings: normalizeOptionalVisibility(
        (rawAssetDefaults.llmSettings ?? rawAssetDefaults.llm_settings) as 'private' | 'shared' | 'app' | undefined,
        APP_CONFIG_FALLBACKS[appId].assetDefaults.llmSettings,
      ),
    },
    analytics: {
      ...APP_CONFIG_FALLBACKS[appId].analytics,
      ...(rawAnalytics as Partial<AppConfig['analytics']>),
      assets: {
        ...APP_CONFIG_FALLBACKS[appId].analytics.assets,
        promptReferencesKey: (
          rawAnalyticsAssets.promptReferencesKey ?? rawAnalyticsAssets.prompt_references_key
        ) as string | null | undefined
          ?? APP_CONFIG_FALLBACKS[appId].analytics.assets.promptReferencesKey,
        narrativeTemplateKey: (
          rawAnalyticsAssets.narrativeTemplateKey ?? rawAnalyticsAssets.narrative_template_key
        ) as string | null | undefined
          ?? APP_CONFIG_FALLBACKS[appId].analytics.assets.narrativeTemplateKey,
        glossaryKey: (
          rawAnalyticsAssets.glossaryKey ?? rawAnalyticsAssets.glossary_key
        ) as string | null | undefined
          ?? APP_CONFIG_FALLBACKS[appId].analytics.assets.glossaryKey,
      },
    },
  };
}

function toAppSummary(app: ApiAppSummary): AppSummary {
  return {
    id: app.id,
    slug: app.slug,
    displayName: app.displayName,
    description: app.description,
    iconUrl: app.iconUrl,
    isActive: app.isActive,
  };
}

function toAppConfig(appId: AppId, config: ApiAppConfig): AppConfig {
  return mergeAppConfig(appId, normalizeAppConfig(appId, config as Record<string, unknown>));
}

export const appsRepository = {
  async getAll(): Promise<AppSummary[]> {
    const data = await apiRequest<ApiAppSummary[]>('/api/apps');
    return data.map(toAppSummary);
  },

  async getConfig(appId: AppId): Promise<AppConfig> {
    const data = await apiRequest<ApiAppConfig>(`/api/apps/${appId}/config`);
    return toAppConfig(appId, data);
  },
};
