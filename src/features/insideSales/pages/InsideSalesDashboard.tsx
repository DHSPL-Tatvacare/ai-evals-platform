import { LayoutDashboard } from 'lucide-react';
import { EmptyState } from '@/components/ui';

export function InsideSalesDashboard() {
  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="shrink-0 pb-4">
        <h1 className="text-lg font-semibold text-[var(--text-primary)]">Dashboard</h1>
      </div>
      <div className="flex-1 flex items-center justify-center">
        <EmptyState
          icon={LayoutDashboard}
          title="Coming soon"
          description="The dashboard will be built in a future phase."
        />
      </div>
    </div>
  );
}
