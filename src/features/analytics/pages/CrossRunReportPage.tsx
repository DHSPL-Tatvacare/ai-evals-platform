import { RefreshCw, LayoutGrid } from 'lucide-react';
import { analyticsLibraryForApp } from '@/config/routes';
import { useCurrentAppId } from '@/hooks';
import { EmptyState, LoadingState, PageSurface } from '@/components/ui';
import { ActionIconButton } from '@/features/evalRuns/components/RunHeaderActions';
import { useReportRuns, useReportRunArtifact } from '@/features/reports/queries/reportsQueries';
import { RunReportSurface } from '@/features/analytics/components/RunReportSurface';
import { decodeApiError, summarizeApiErrorBody } from '@/features/orchestration/contracts/errorDecoder';
import type { PlatformCrossRunPayload } from '@/types/platformReports';

export function CrossRunReportPage() {
  const appId = useCurrentAppId();
  const back = { to: analyticsLibraryForApp(appId), label: 'Analytics' };

  const runsQuery = useReportRuns({ appId, scope: 'cross_run', limit: 1 });
  const latestRun = runsQuery.data?.find((r) => r.status === 'completed') ?? runsQuery.data?.[0] ?? null;

  const artifactQuery = useReportRunArtifact<PlatformCrossRunPayload>(latestRun?.id ?? null);

  const isLoading = runsQuery.isLoading || (latestRun !== null && artifactQuery.isLoading);
  const error = runsQuery.error ?? artifactQuery.error;

  if (isLoading) {
    return (
      <PageSurface icon={LayoutGrid} title="Cross-Run Report" back={back} showHeader={false}>
        <LoadingState message="Loading report…" />
      </PageSurface>
    );
  }

  if (error) {
    const decoded = decodeApiError(error);
    return (
      <PageSurface icon={LayoutGrid} title="Cross-Run Report" back={back}>
        <EmptyState
          icon={LayoutGrid}
          title="Failed to load report"
          description={summarizeApiErrorBody(decoded, 'An unexpected error occurred.')}
          fill
        />
      </PageSurface>
    );
  }

  if (!latestRun || !artifactQuery.data) {
    return (
      <PageSurface icon={LayoutGrid} title="Cross-Run Report" back={back}>
        <EmptyState
          icon={LayoutGrid}
          title="No cross-run report yet"
          description="Generate a cross-run report to see analytics across runs."
          fill
        />
      </PageSurface>
    );
  }

  return (
    <PageSurface
      icon={LayoutGrid}
      title="Cross-Run Report"
      back={back}
      actions={
        <ActionIconButton
          icon={RefreshCw}
          label="Refresh"
          tooltip="Refresh"
          onClick={() => { void runsQuery.refetch(); void artifactQuery.refetch(); }}
          disabled={runsQuery.isFetching || artifactQuery.isFetching}
          spinning={runsQuery.isFetching || artifactQuery.isFetching}
        />
      }
    >
      <RunReportSurface report={artifactQuery.data} runId={latestRun.id} actions={null} />
    </PageSurface>
  );
}
