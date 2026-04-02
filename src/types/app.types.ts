/**
 * App Types & Metadata
 * Central definitions for multi-app support
 */

export type AppId = 'voice-rx' | 'kaira-bot' | 'inside-sales';
export const APP_IDS: AppId[] = ['voice-rx', 'kaira-bot', 'inside-sales'];

export interface AppSummary {
  id: string;
  slug: string;
  displayName: string;
  description: string;
  iconUrl: string;
  isActive: boolean;
}

export interface AppMetadata {
  id: AppId;
  name: string;
  icon: string;
  description: string;
  searchPlaceholder: string;
  newItemLabel: string;
}

export interface AppVariableConfig {
  key: string;
  displayName: string;
  description: string;
  category: string;
}

export interface AppDynamicVariableSources {
  registry: boolean;
  listingApiPaths: boolean;
}

export interface AppFeaturesConfig {
  hasRules: boolean;
  hasRubricMode: boolean;
  hasCsvImport: boolean;
  hasAdversarial: boolean;
  hasTranscription: boolean;
  hasBatchEval: boolean;
  hasHumanReview: boolean;
}

export interface AppRulesConfig {
  catalogSource: string;
  catalogKey: string;
  autoMatch: boolean;
}

export interface AppEvaluatorConfig {
  defaultVisibility: 'private' | 'app';
  defaultModel: string;
  variables: AppVariableConfig[];
  dynamicVariableSources: AppDynamicVariableSources;
}

export interface AppAssetDefaults {
  evaluator: 'private' | 'app';
  prompt: 'private' | 'app';
  schema: 'private' | 'app';
  adversarialContract: 'private' | 'app';
  llmSettings: 'private' | 'app';
}

export interface AppEvalRunConfig {
  supportedTypes: string[];
}

export interface AppConfig {
  displayName: string;
  icon: string;
  description: string;
  features: AppFeaturesConfig;
  rules: AppRulesConfig;
  evaluator: AppEvaluatorConfig;
  assetDefaults: AppAssetDefaults;
  evalRun: AppEvalRunConfig;
}

export interface RuleCatalogEntry {
  ruleId: string;
  ruleText: string;
  section: string;
  tags: string[];
  goalIds: string[];
  evaluationScopes: string[];
  [key: string]: unknown;
}

export interface RuleCatalogResponse {
  rules: RuleCatalogEntry[];
}

export const APPS: Record<AppId, AppMetadata> = {
  'voice-rx': {
    id: 'voice-rx',
    name: 'Voice Rx',
    icon: '/voice-rx-icon.jpeg',
    description: 'Audio file evaluation tool',
    searchPlaceholder: 'Search evaluations...',
    newItemLabel: 'New',
  },
  'kaira-bot': {
    id: 'kaira-bot',
    name: 'Kaira Bot',
    icon: '/kaira-icon.svg',
    description: 'Health chat bot assistant',
    searchPlaceholder: 'Search chats...',
    newItemLabel: 'New Chat',
  },
  'inside-sales': {
    id: 'inside-sales',
    name: 'Inside Sales',
    icon: '/inside-sales-icon.svg',
    description: 'Inside sales call quality evaluation',
    searchPlaceholder: 'Search calls...',
    newItemLabel: 'New Run',
  },
};

export const DEFAULT_APP: AppId = 'voice-rx';

export const APP_CONFIG_FALLBACKS: Record<AppId, AppConfig> = {
  'voice-rx': {
    displayName: APPS['voice-rx'].name,
    icon: APPS['voice-rx'].icon,
    description: APPS['voice-rx'].description,
    features: {
      hasRules: false,
      hasRubricMode: false,
      hasCsvImport: false,
      hasAdversarial: false,
      hasTranscription: true,
      hasBatchEval: false,
      hasHumanReview: false,
    },
    rules: {
      catalogSource: 'settings',
      catalogKey: 'rule-catalog',
      autoMatch: false,
    },
    evaluator: {
      defaultVisibility: 'private',
      defaultModel: '',
      variables: [],
      dynamicVariableSources: {
        registry: true,
        listingApiPaths: true,
      },
    },
    assetDefaults: {
      evaluator: 'private',
      prompt: 'private',
      schema: 'private',
      adversarialContract: 'private',
      llmSettings: 'private',
    },
    evalRun: {
      supportedTypes: [],
    },
  },
  'kaira-bot': {
    displayName: APPS['kaira-bot'].name,
    icon: APPS['kaira-bot'].icon,
    description: APPS['kaira-bot'].description,
    features: {
      hasRules: true,
      hasRubricMode: false,
      hasCsvImport: false,
      hasAdversarial: true,
      hasTranscription: false,
      hasBatchEval: true,
      hasHumanReview: false,
    },
    rules: {
      catalogSource: 'settings',
      catalogKey: 'rule-catalog',
      autoMatch: true,
    },
    evaluator: {
      defaultVisibility: 'private',
      defaultModel: '',
      variables: [],
      dynamicVariableSources: {
        registry: true,
        listingApiPaths: false,
      },
    },
    assetDefaults: {
      evaluator: 'private',
      prompt: 'private',
      schema: 'private',
      adversarialContract: 'app',
      llmSettings: 'private',
    },
    evalRun: {
      supportedTypes: [],
    },
  },
  'inside-sales': {
    displayName: APPS['inside-sales'].name,
    icon: APPS['inside-sales'].icon,
    description: APPS['inside-sales'].description,
    features: {
      hasRules: false,
      hasRubricMode: true,
      hasCsvImport: true,
      hasAdversarial: false,
      hasTranscription: true,
      hasBatchEval: true,
      hasHumanReview: false,
    },
    rules: {
      catalogSource: 'settings',
      catalogKey: 'rule-catalog',
      autoMatch: false,
    },
    evaluator: {
      defaultVisibility: 'private',
      defaultModel: '',
      variables: [],
      dynamicVariableSources: {
        registry: true,
        listingApiPaths: false,
      },
    },
    assetDefaults: {
      evaluator: 'private',
      prompt: 'private',
      schema: 'private',
      adversarialContract: 'private',
      llmSettings: 'private',
    },
    evalRun: {
      supportedTypes: [],
    },
  },
};

export function getAppMetadataFromConfig(appId: AppId, config?: AppConfig | null): AppMetadata {
  const fallback = APPS[appId];
  if (!config) return fallback;

  return {
    id: appId,
    name: config.displayName || fallback.name,
    icon: config.icon || fallback.icon,
    description: config.description || fallback.description,
    searchPlaceholder: fallback.searchPlaceholder,
    newItemLabel: fallback.newItemLabel,
  };
}

export function mergeAppConfig(appId: AppId, config?: Partial<AppConfig> | null): AppConfig {
  const fallback = APP_CONFIG_FALLBACKS[appId];
  if (!config) return fallback;

  return {
    ...fallback,
    ...config,
    features: {
      ...fallback.features,
      ...config.features,
    },
    rules: {
      ...fallback.rules,
      ...config.rules,
    },
    evaluator: {
      ...fallback.evaluator,
      ...config.evaluator,
      variables: config.evaluator?.variables ?? fallback.evaluator.variables,
      dynamicVariableSources: {
        ...fallback.evaluator.dynamicVariableSources,
        ...config.evaluator?.dynamicVariableSources,
      },
    },
    assetDefaults: {
      ...fallback.assetDefaults,
      ...config.assetDefaults,
    },
    evalRun: {
      ...fallback.evalRun,
      ...config.evalRun,
    },
  };
}
