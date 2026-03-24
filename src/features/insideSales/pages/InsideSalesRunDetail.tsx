import { GitCompareArrows } from 'lucide-react';
import { EmptyState } from '@/components/ui';

export function InsideSalesRunDetail() {
  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="shrink-0 pb-4">
        <h1 className="text-lg font-semibold text-[var(--text-primary)]">Run Detail</h1>
      </div>
      <div className="flex-1 flex items-center justify-center">
        <EmptyState
          icon={GitCompareArrows}
          title="Coming soon"
          description="Run detail view will be built in a future phase."
        />
      </div>
    </div>
  );
}
