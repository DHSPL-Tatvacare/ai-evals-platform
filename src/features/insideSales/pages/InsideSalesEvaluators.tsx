import { FileText } from 'lucide-react';
import { EmptyState } from '@/components/ui';

export function InsideSalesEvaluators() {
  return (
    <div className="flex flex-col h-[calc(100vh-var(--header-height))]">
      <div className="shrink-0 pb-4">
        <h1 className="text-lg font-semibold text-[var(--text-primary)]">Evaluators</h1>
      </div>
      <div className="flex-1 flex items-center justify-center">
        <EmptyState
          icon={FileText}
          title="Coming soon"
          description="Evaluators configuration will be built in a future phase."
        />
      </div>
    </div>
  );
}
