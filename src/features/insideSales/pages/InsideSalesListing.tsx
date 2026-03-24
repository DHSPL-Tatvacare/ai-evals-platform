import { LayoutGrid } from 'lucide-react';
import { EmptyState } from '@/components/ui';

export function InsideSalesListing() {
  return (
    <div className="flex flex-col h-[calc(100vh-var(--header-height))]">
      <div className="shrink-0 pb-4">
        <h1 className="text-lg font-semibold text-[var(--text-primary)]">Calls</h1>
      </div>
      <div className="flex-1 flex items-center justify-center">
        <EmptyState
          icon={LayoutGrid}
          title="Coming soon"
          description="The call listing will be built in Phase 2."
        />
      </div>
    </div>
  );
}
