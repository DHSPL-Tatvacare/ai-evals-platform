import type { LlmProvider } from '@/services/api/llmCredentialsApi';
import {
  LLM_PROVIDER_LABELS,
  LLM_PROVIDER_LOGOS,
  LLM_PROVIDER_LOGOS_DARK,
} from '@/constants/llmProviders';
import { useResolvedTheme } from '@/hooks/useResolvedTheme';
import { cn } from '@/utils';

interface LLMProviderLogoProps {
  provider: LlmProvider;
  size?: number;
  className?: string;
}

export function LLMProviderLogo({
  provider,
  size = 20,
  className,
}: LLMProviderLogoProps) {
  const theme = useResolvedTheme();
  const src =
    (theme === 'dark' && LLM_PROVIDER_LOGOS_DARK[provider]) ||
    LLM_PROVIDER_LOGOS[provider];
  return (
    <img
      src={src}
      alt={`${LLM_PROVIDER_LABELS[provider]} logo`}
      width={size}
      height={size}
      className={cn('shrink-0 rounded-[4px] object-contain', className)}
      style={{ width: size, height: size }}
    />
  );
}
