import type { ReactNode } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';
import { EmptyState, Button } from '@/components/ui';
import type { Slice } from '@/stores/costStore';

interface SliceStateBoundaryProps<T> {
  slice: Slice<T> | (Slice<T> & { page: number });
  children: (data: T) => ReactNode;
  onRetry?: () => void;
  loadingLabel?: string;
}

export function SliceStateBoundary<T>({
  slice,
  children,
  onRetry,
  loadingLabel = 'Loading…',
}: SliceStateBoundaryProps<T>) {
  if (slice.status === 'idle' || slice.status === 'loading') {
    return (
      <div className="flex items-center justify-center gap-2 py-16 text-sm text-[var(--text-secondary)]">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span>{loadingLabel}</span>
      </div>
    );
  }
  if (slice.status === 'error') {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Couldn't load data"
        description={slice.error || 'Request failed'}
      >
        {onRetry && (
          <Button variant="secondary" size="sm" onClick={onRetry}>
            Retry
          </Button>
        )}
      </EmptyState>
    );
  }
  if (!slice.data) {
    return null;
  }
  return <>{children(slice.data)}</>;
}
