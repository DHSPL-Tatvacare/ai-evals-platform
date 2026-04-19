import { cn } from '@/utils';

const PROVIDER_TOKENS: Record<string, string> = {
  openai: '--color-provider-openai',
  anthropic: '--color-provider-anthropic',
  gemini: '--color-provider-gemini',
  google: '--color-provider-gemini',
  azure: '--color-provider-azure',
  azure_openai: '--color-provider-azure',
};

const APP_TOKENS: Record<string, string> = {
  'voice-rx': '--color-app-voicerx',
  voicerx: '--color-app-voicerx',
  'kaira-bot': '--color-app-kaira',
  kaira: '--color-app-kaira',
  'inside-sales': '--color-app-insidesales',
  insidesales: '--color-app-insidesales',
  report: '--color-app-report',
};

function tokenFor(registry: Record<string, string>, key: string): string | null {
  const normalized = key.toLowerCase().replace(/\s+/g, '-');
  return registry[normalized] ?? null;
}

interface TagProps {
  value: string;
  className?: string;
}

export function ProviderTag({ value, className }: TagProps) {
  const token = tokenFor(PROVIDER_TOKENS, value);
  const style = token
    ? {
        backgroundColor: `color-mix(in srgb, var(${token}) 18%, transparent)`,
        color: `var(${token})`,
      }
    : undefined;
  return (
    <span
      style={style}
      className={cn(
        'inline-flex items-center rounded-[4px] px-1.5 py-0.5 text-[11px] font-medium',
        !token && 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]',
        className,
      )}
    >
      {value}
    </span>
  );
}

export function AppTag({ value, className }: TagProps) {
  const token = tokenFor(APP_TOKENS, value);
  const style = token
    ? {
        backgroundColor: `color-mix(in srgb, var(${token}) 18%, transparent)`,
        color: `var(${token})`,
      }
    : undefined;
  return (
    <span
      style={style}
      className={cn(
        'inline-flex items-center rounded-[4px] px-1.5 py-0.5 text-[11px] font-medium',
        !token && 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]',
        className,
      )}
    >
      {value}
    </span>
  );
}
