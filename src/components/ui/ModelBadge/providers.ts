/**
 * LLM Provider icon registry
 * Maps provider names to their icon paths
 */

export type LLMProvider = 'gemini' | 'openai' | 'azure_openai' | 'anthropic' | 'unknown';

export const providerIcons: Record<LLMProvider, string> = {
  gemini: '/images/gemini.svg',
  openai: '/images/openai.svg',
  azure_openai: '/images/azure.svg',
  anthropic: '/images/anthropic.svg',
  unknown: '/images/gemini.svg', // fallback
};

export const providerLabels: Record<LLMProvider, string> = {
  gemini: 'Gemini',
  openai: 'OpenAI',
  azure_openai: 'Azure OpenAI',
  anthropic: 'Anthropic',
  unknown: 'AI',
};

/**
 * Detect provider from model name string
 */
export function detectProvider(modelName: string): LLMProvider {
  const lower = modelName.toLowerCase();

  if (lower.includes('gemini')) return 'gemini';
  if (lower.includes('azure')) return 'azure_openai';
  if (lower.includes('gpt') || lower.includes('openai')) return 'openai';
  if (lower.includes('claude') || lower.includes('anthropic')) return 'anthropic';

  return 'unknown';
}
