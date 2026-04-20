import { cn } from '@/utils';
import { PROVIDER_TOKENS, APP_TOKENS, tokenFor } from './providerTokens';

interface TagProps {
  value: string;
  className?: string;
  withDot?: boolean;
}

function BaseTag({ value, className, withDot, token }: TagProps & { token: string | null }) {
  const style = token
    ? {
        backgroundColor: `color-mix(in srgb, var(${token}) 18%, transparent)`,
        color: `var(${token})`,
      }
    : undefined;
  const dotStyle = token ? { backgroundColor: `var(${token})` } : undefined;
  return (
    <span
      style={style}
      className={cn(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-[4px] px-1.5 py-0.5 text-[11px] font-medium',
        !token && 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]',
        className,
      )}
    >
      {withDot && <span className="h-1.5 w-1.5 rounded-full" style={dotStyle} />}
      {value}
    </span>
  );
}

export function ProviderTag({ value, className, withDot = true }: TagProps) {
  return <BaseTag value={value} className={className} withDot={withDot} token={tokenFor(PROVIDER_TOKENS, value)} />;
}

export function AppTag({ value, className, withDot = true }: TagProps) {
  return <BaseTag value={value} className={className} withDot={withDot} token={tokenFor(APP_TOKENS, value)} />;
}
