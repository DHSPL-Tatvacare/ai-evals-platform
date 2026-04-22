import { Gauge } from 'lucide-react';
import { PageSurface } from '@/components/ui';
import { AppEvaluatorsPage } from '@/features/evals';

export function KairaEvaluatorsPage() {
  return (
    <PageSurface icon={Gauge} title="Evaluators">
      <AppEvaluatorsPage embedded />
    </PageSurface>
  );
}
