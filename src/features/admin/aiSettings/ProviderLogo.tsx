import type { LLMProvider } from '@/services/api/aiSettingsApi';
import { cn } from '@/utils';

/**
 * Brand-color provider logos. Sourced verbatim from the Jan AI repo at
 * `web-app/public/images/model-provider/<name>.svg` and copied into
 * `public/llm-logos/`. Rendered via `<img>` so the full provider palette
 * (Anthropic terra tile, Gemini gradient, OpenAI green field, Azure blue)
 * survives intact — these are full-color SVGs, not `currentColor` masks.
 *
 * Dark mode: the SVGs already include their own backgrounds and contrast,
 * so they render correctly on either theme without filtering. We wrap them
 * in a rounded container so the brand tile sits naturally next to text.
 */

const LOGO_FILE: Record<LLMProvider, string> = {
  openai: '/llm-logos/openai.svg',
  azure_openai: '/llm-logos/azure.svg',
  anthropic: '/llm-logos/anthropic.svg',
  gemini: '/llm-logos/gemini.svg',
};

const PROVIDER_NAMES: Record<LLMProvider, string> = {
  openai: 'OpenAI',
  azure_openai: 'Azure OpenAI',
  anthropic: 'Anthropic',
  gemini: 'Gemini',
};

interface ProviderLogoProps {
  provider: LLMProvider;
  size?: number;
  className?: string;
}

export function ProviderLogo({
  provider,
  size = 20,
  className,
}: ProviderLogoProps) {
  return (
    <img
      src={LOGO_FILE[provider]}
      alt={`${PROVIDER_NAMES[provider]} logo`}
      width={size}
      height={size}
      className={cn(
        'shrink-0 rounded-[4px] object-contain',
        className,
      )}
      style={{ width: size, height: size }}
    />
  );
}
