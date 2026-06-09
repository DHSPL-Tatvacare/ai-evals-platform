import { AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui';
import { cn } from '@/utils';

interface ErrorFallbackProps {
  error?: Error;
  onRetry?: () => void;
  title?: string;
  compact?: boolean;
}

export function ErrorFallback({ error, onRetry, title = 'This page flatlined', compact = false }: ErrorFallbackProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center text-center',
        compact ? 'p-6' : 'min-h-dvh p-12'
      )}
    >
      {compact ? (
        <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-full bg-[var(--color-error-light)]">
          <AlertCircle className="h-5 w-5 text-[var(--color-error)]" />
        </div>
      ) : (
        <img
          src="/error-illustration.png"
          alt=""
          aria-hidden="true"
          className="mb-6 h-auto max-h-[48vh] w-auto max-w-[88vw] select-none"
          draggable={false}
        />
      )}

      <h2 className={cn(
        'font-semibold text-[var(--text-primary)]',
        compact ? 'text-base' : 'text-lg'
      )}>
        {title}
      </h2>
      
      {compact ? (
        error && (
          <p className="mt-2 text-[12px] text-[var(--text-secondary)]">
            {error.message}
          </p>
        )
      ) : (
        <p className="mt-2 whitespace-nowrap text-sm font-medium text-[var(--text-secondary)]">
          We&rsquo;ve called a code blue &mdash; try again in a moment.
        </p>
      )}
      
      {onRetry && (
        <Button
          variant="secondary"
          size={compact ? 'sm' : 'md'}
          onClick={onRetry}
          className="mt-4"
        >
          <RefreshCw className="h-4 w-4" />
          Try again
        </Button>
      )}
    </div>
  );
}
