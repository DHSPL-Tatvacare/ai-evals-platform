import { Plug } from 'lucide-react';

import {
  CONNECTION_PROVIDER_LABELS,
  CONNECTION_PROVIDER_LOGOS,
} from '@/constants/connectionProviders';
import { cn } from '@/utils';

interface ConnectionProviderLogoProps {
  provider: string;
  size?: number;
  className?: string;
}

function labelFor(provider: string): string {
  return CONNECTION_PROVIDER_LABELS[provider] ?? provider;
}

export function ConnectionProviderLogo({
  provider,
  size = 20,
  className,
}: ConnectionProviderLogoProps) {
  const logo = CONNECTION_PROVIDER_LOGOS[provider];
  if (logo) {
    return (
      <img
        src={logo}
        alt={`${labelFor(provider)} logo`}
        width={size}
        height={size}
        className={cn('shrink-0 rounded-[4px] object-contain', className)}
        style={{ width: size, height: size }}
      />
    );
  }
  return (
    <span
      aria-label={`${labelFor(provider)} logo`}
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-[4px] bg-[var(--bg-secondary)] text-[var(--text-secondary)]',
        className,
      )}
      style={{ width: size, height: size }}
    >
      <Plug width={Math.round(size * 0.6)} height={Math.round(size * 0.6)} />
    </span>
  );
}
