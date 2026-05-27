import type { LlmProvider } from '@/services/api/llmCredentialsApi';

export const LLM_PROVIDER_LABELS: Record<LlmProvider, string> = {
  openai: 'OpenAI',
  azure_openai: 'Azure OpenAI',
  anthropic: 'Anthropic',
  gemini: 'Gemini',
  // Backend/catalog key stays 'vertex'; UI uses Google's current product brand.
  vertex: 'Gemini Agent Platform',
  bedrock: 'AWS Bedrock',
  sarvam: 'Sarvam AI',
};

// Default (light-mode) logo per provider.
export const LLM_PROVIDER_LOGOS: Record<LlmProvider, string> = {
  openai: '/llm-logos/openai.svg',
  azure_openai: '/llm-logos/azure.svg',
  anthropic: '/llm-logos/anthropic.svg',
  gemini: '/llm-logos/gemini.svg',
  vertex: '/llm-logos/gemini.svg',
  bedrock: '/llm-logos/bedrock.svg',
  sarvam: '/llm-logos/sarvam-light.jpeg',
};

// Dark-mode override, only for providers whose mark needs a light-on-dark
// variant. Providers absent here fall back to LLM_PROVIDER_LOGOS in both themes.
export const LLM_PROVIDER_LOGOS_DARK: Partial<Record<LlmProvider, string>> = {
  sarvam: '/llm-logos/sarvam-dark.png',
};

