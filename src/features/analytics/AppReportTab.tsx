import type { AppId } from '@/types';
import { FileBarChart } from 'lucide-react';
import { EmptyState } from '@/components/ui';
import ReportTab from '@/features/evalRuns/components/report/ReportTab';
import { getAnalyticsConfig } from './registry';

interface Props {
  appId: AppId;
  runId: string;
}

export function AppReportTab({ appId, runId }: Props) {
  const config = getAnalyticsConfig(appId);

  if (!config.report) {
    return (
      <EmptyState
        icon={FileBarChart}
        title="Reports are not available"
        description="This app does not expose a report renderer yet."
        compact
      />
    );
  }

  return (
    <ReportTab
      appId={appId}
      runId={runId}
      supportsPdf={config.report.supportsPdf}
      renderReport={(report, actions) => config.report?.render(report, { appId, runId, actions }) ?? null}
    />
  );
}
