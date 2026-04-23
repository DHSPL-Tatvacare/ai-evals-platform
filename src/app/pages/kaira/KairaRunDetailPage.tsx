import { ListChecks } from 'lucide-react';
import { routes } from '@/config/routes';
import { EvalRunDetail } from '@/features/evalRuns';

export function KairaRunDetailPage() {
  return (
    <EvalRunDetail
      surface={{
        icon: ListChecks,
        back: { to: routes.kaira.runs, label: 'Runs' },
      }}
    />
  );
}
