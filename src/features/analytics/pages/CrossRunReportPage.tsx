import { useCallback, useMemo, useState } from 'react';
import { LayoutGrid, Loader2, RefreshCw, Sparkles } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';

import { analyticsLibraryForApp } from '@/config/routes';
import { useCurrentAppId } from '@/hooks';
import { Button, EmptyState, LegacyLlmConfigCompat, LoadingState, PageSurface, Select, type SelectOption } from '@/components/ui';
import { ActionIconButton } from '@/features/evalRuns/components/RunHeaderActions';
import { invalidateReportRuns, useReportConfigs, useReportRunArtifact, useReportRuns } from '@/features/reports/queries/reportsQueries';
import { RunReportSurface } from '@/features/analytics/components/RunReportSurface';
import { decodeApiError, summarizeApiErrorBody } from '@/features/orchestration/contracts/errorDecoder';
import { submitAndPollJob } from '@/services/api/jobPolling';
import { notificationService } from '@/services/notifications';
import { SettingsSlideOver } from '@/features/settings/components/SettingsSlideOver';
import type { LLMProvider } from '@/services/api/aiSettingsApi';
import type { PlatformCrossRunPayload } from '@/types/platformReports';

// ── Local generate overlay ────────────────────────────────────────────────────

interface GenerateOverlayProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  reportConfigOptions: SelectOption[];
  selectedReportId: string | null;
  onSelectReportId: (id: string) => void;
  provider: LLMProvider | '';
  onProviderChange: (p: LLMProvider) => void;
  model: string;
  onModelChange: (m: string) => void;
  isRegenerating: boolean;
}

function GenerateOverlay({
  isOpen,
  onClose,
  onConfirm,
  reportConfigOptions,
  selectedReportId,
  onSelectReportId,
  provider,
  onProviderChange,
  model,
  onModelChange,
  isRegenerating,
}: GenerateOverlayProps) {
  const title = isRegenerating ? 'Regenerate cross-run report' : 'Generate cross-run report';
  const canSubmit = Boolean(selectedReportId) && Boolean(model);

  return (
    <SettingsSlideOver
      isOpen={isOpen}
      onClose={onClose}
      title={title}
      description="Pick a blueprint and a model to generate an analytics report across all runs."
      onSubmit={onConfirm}
      submitLabel="Generate"
      canSubmit={canSubmit}
      widthClassName="w-[720px] max-w-[92vw]"
      footerContent={
        <div className={`text-[12px] ${!model ? 'text-[var(--color-warning)]' : 'text-[var(--text-muted)]'}`}>
          {!model ? 'Select a model to continue.' : 'Report will aggregate the latest single-run report artifacts.'}
        </div>
      }
    >
      <div className="space-y-5">
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-secondary)]">
            Blueprint
          </div>
          {reportConfigOptions.length > 1 ? (
            <Select
              value={selectedReportId ?? ''}
              onChange={onSelectReportId}
              options={reportConfigOptions}
              placeholder="Choose a blueprint"
              className="w-full"
            />
          ) : (
            <div className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)]">
              {reportConfigOptions[0]?.label ?? 'Cross-Run Report'}
            </div>
          )}
        </div>

        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-secondary)]">
            Provider and model
          </div>
          <LegacyLlmConfigCompat
            callSite="report_generation"
            provider={provider}
            onProviderChange={onProviderChange}
            model={model}
            onModelChange={onModelChange}
          />
        </div>
      </div>
    </SettingsSlideOver>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function CrossRunReportPage() {
  const appId = useCurrentAppId();
  const queryClient = useQueryClient();
  const back = { to: analyticsLibraryForApp(appId), label: 'Analytics' };

  const runsQuery = useReportRuns({ appId, scope: 'cross_run', limit: 1 });
  const latestRun = runsQuery.data?.find((r) => r.status === 'completed') ?? runsQuery.data?.[0] ?? null;

  const artifactQuery = useReportRunArtifact<PlatformCrossRunPayload>(latestRun?.id ?? null);

  const configsQuery = useReportConfigs(appId, 'cross_run');
  const configs = useMemo(() => configsQuery.data ?? [], [configsQuery.data]);

  // Auto-select the sole/default blueprint; never force a choice when there's only one.
  const defaultConfigId = useMemo(
    () => configs.find((c) => c.isDefault)?.reportId ?? configs[0]?.reportId ?? null,
    [configs],
  );

  const configOptions = useMemo<SelectOption[]>(
    () =>
      configs.map((c) => ({
        value: c.reportId,
        label: c.isDefault ? `${c.name} (Default)` : c.name,
      })),
    [configs],
  );

  // Overlay state
  const [showOverlay, setShowOverlay] = useState(false);
  const [overlayReportId, setOverlayReportId] = useState<string | null>(null);
  const [reportProvider, setReportProvider] = useState<LLMProvider | ''>('');
  const [reportModel, setReportModel] = useState('');

  // Generation in-flight state
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const [progressMsg, setProgressMsg] = useState('');

  const openOverlay = useCallback(() => {
    setOverlayReportId(defaultConfigId);
    setShowOverlay(true);
  }, [defaultConfigId]);

  const handleGenerate = useCallback(async () => {
    if (!overlayReportId) return;

    setShowOverlay(false);
    setGenerating(true);
    setGenError(null);
    setProgressMsg('Submitting report job…');

    try {
      const completedJob = await submitAndPollJob(
        'generate-cross-run-report',
        {
          app_id: appId,
          report_id: overlayReportId,
          provider: reportProvider || undefined,
          model: reportModel || undefined,
          limit: 50,
        },
        {
          pollIntervalMs: 2000,
          onProgress: (progress) => {
            setProgressMsg(progress.message || 'Generating cross-run report…');
          },
        },
      );

      if (completedJob.status !== 'completed') {
        throw new Error(completedJob.errorMessage || 'Cross-run report generation failed');
      }

      await invalidateReportRuns(queryClient, { appId, scope: 'cross_run' });
      setGenerating(false);
      notificationService.success('Cross-run report generated');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Cross-run report generation failed';
      setGenError(message);
      setGenerating(false);
      notificationService.error(message);
    } finally {
      setProgressMsg('');
    }
  }, [appId, overlayReportId, queryClient, reportModel, reportProvider]);

  const hasReport = Boolean(latestRun && artifactQuery.data);
  const isLoading = runsQuery.isLoading || (latestRun !== null && artifactQuery.isLoading);
  const loadError = runsQuery.error ?? artifactQuery.error;

  if (isLoading) {
    return (
      <PageSurface icon={LayoutGrid} title="Cross-Run Report" back={back} showHeader={false}>
        <LoadingState message="Loading report…" />
      </PageSurface>
    );
  }

  if (loadError) {
    const decoded = decodeApiError(loadError);
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

  const refreshAction = (
    <ActionIconButton
      icon={RefreshCw}
      label="Refresh"
      tooltip="Refresh"
      onClick={() => { void runsQuery.refetch(); void artifactQuery.refetch(); }}
      disabled={runsQuery.isFetching || artifactQuery.isFetching}
      spinning={runsQuery.isFetching || artifactQuery.isFetching}
    />
  );

  const regenerateAction = hasReport ? (
    <ActionIconButton
      icon={Sparkles}
      label="Regenerate"
      tooltip="Regenerate report"
      onClick={openOverlay}
      disabled={generating}
    />
  ) : null;

  // In-progress banner rendered in place of the EmptyState description area
  const progressBanner = generating ? (
    <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
      <Loader2 className="h-4 w-4 animate-spin" />
      <span>{progressMsg || 'Generating cross-run report…'}</span>
    </div>
  ) : null;

  if (!hasReport) {
    return (
      <>
        <PageSurface
          icon={LayoutGrid}
          title="Cross-Run Report"
          back={back}
          actions={refreshAction}
        >
          <EmptyState
            icon={LayoutGrid}
            title="No cross-run report yet"
            description={
              genError
                ? genError
                : generating
                  ? undefined
                  : 'Generate a cross-run report to see analytics across runs.'
            }
            fill
          >
            {progressBanner}
            {!generating && (
              <Button onClick={openOverlay} disabled={generating}>
                <Sparkles className="h-4 w-4" />
                Generate report
              </Button>
            )}
          </EmptyState>
        </PageSurface>

        <GenerateOverlay
          isOpen={showOverlay}
          onClose={() => setShowOverlay(false)}
          onConfirm={() => void handleGenerate()}
          reportConfigOptions={configOptions}
          selectedReportId={overlayReportId}
          onSelectReportId={setOverlayReportId}
          provider={reportProvider}
          onProviderChange={(p) => { setReportProvider(p); setReportModel(''); }}
          model={reportModel}
          onModelChange={setReportModel}
          isRegenerating={false}
        />
      </>
    );
  }

  return (
    <>
      <PageSurface
        icon={LayoutGrid}
        title="Cross-Run Report"
        back={back}
        actions={
          <div className="flex items-center gap-2">
            {regenerateAction}
            {refreshAction}
          </div>
        }
      >
        {artifactQuery.data && (
          <RunReportSurface report={artifactQuery.data} runId={latestRun!.id} actions={null} />
        )}
      </PageSurface>

      <GenerateOverlay
        isOpen={showOverlay}
        onClose={() => setShowOverlay(false)}
        onConfirm={() => void handleGenerate()}
        reportConfigOptions={configOptions}
        selectedReportId={overlayReportId}
        onSelectReportId={setOverlayReportId}
        provider={reportProvider}
        onProviderChange={(p) => { setReportProvider(p); setReportModel(''); }}
        model={reportModel}
        onModelChange={setReportModel}
        isRegenerating={true}
      />
    </>
  );
}
