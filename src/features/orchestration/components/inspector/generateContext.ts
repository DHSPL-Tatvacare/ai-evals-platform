import type {
  GeneratePromptBody,
  GenerateSchemaBody,
} from '@/services/api/llmAssistApi';
import type { LLMProvider } from '@/services/api/aiSettingsApi';
import type { UpstreamField } from '@/services/api/orchestration';

/** Variable NAMES (paths) the draft may reference. Never sample values —
 *  resolved cohort/clinical data must not leave the platform for a draft. */
export function variableNamesForGenerate(
  fields: readonly UpstreamField[],
  excluded?: ReadonlySet<string>,
): string[] {
  return fields.map((f) => f.path).filter((p) => !excluded?.has(p));
}

/** Fold the variable names into the existing `user_idea` text — the only
 *  channel for upstream context, since the llm-assist contract is fixed. */
export function composeGenerateIdea(
  userIdea: string,
  variableNames: readonly string[],
): string {
  if (variableNames.length === 0) return userIdea;
  const tokens = variableNames.map((n) => `{{${n}}}`).join(', ');
  const suffix = `You may reference these variables: ${tokens}.`;
  const trimmed = userIdea.trim();
  return trimmed ? `${trimmed}\n\n${suffix}` : suffix;
}

interface GenerateArgs {
  provider: LLMProvider;
  model: string;
  userIdea: string;
  fields: readonly UpstreamField[];
  excluded?: ReadonlySet<string>;
}

export function buildGeneratePromptBody(args: GenerateArgs): GeneratePromptBody {
  return {
    provider: args.provider,
    model: args.model,
    promptType: 'extraction',
    userIdea: composeGenerateIdea(
      args.userIdea,
      variableNamesForGenerate(args.fields, args.excluded),
    ),
  };
}

export function buildGenerateSchemaBody(args: GenerateArgs): GenerateSchemaBody {
  return {
    provider: args.provider,
    model: args.model,
    promptType: 'extraction',
    userIdea: composeGenerateIdea(
      args.userIdea,
      variableNamesForGenerate(args.fields, args.excluded),
    ),
  };
}
