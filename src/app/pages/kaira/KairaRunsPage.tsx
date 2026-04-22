import { ListChecks } from 'lucide-react';
import { PageSurface } from '@/components/ui';
import { EvalRunList } from '@/features/evalRuns';

export function KairaRunsPage() {
  return (
    <PageSurface icon={ListChecks} title="All Runs">
      <EvalRunList embedded />
    </PageSurface>
  );
}
