import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Clock, Download, FileBarChart, Globe2, Loader2, Sparkles } from 'lucide-react';
import type { AppId, AssetVisibility, LLMProvider, ReportConfigSummary, ReportRunSummary } from '@/types';
import { Button, EmptyState, LLMConfigSection, Modal, VisibilityBadge, VisibilityToggle } from '@/components/ui';
import { reportsApi } from '@/services/api/reportsApi';
import { pollJobUntilComplete, submitAndPollJob, type JobProgress } from '@/services/api/jobPolling';
import { notificationService } from '@/services/notifications';
import { hasProviderCredentials, LLM_PROVIDERS, useLLMSettingsStore } from '@/stores';
import { usePermission } from '@/utils/permissions';

interface ReportMetadataLike {
  llmProvider?: string | null;
  llmModel?: string | null;
}

interface ReportPayloadLike {
  metadata?: ReportMetadataLike | null;
}

interface Props<TReport> {
  appId: AppId;
  runId: string;
  supportsPdf?: boolean;
  renderReport: (report: TReport, actions: ReactNode) => ReactNode;
}

type Status = 'loading' | 'idle' | 'generating' | 'ready' | 'error';

function getReportMetadata<TReport extends ReportPayloadLike>(report: TReport | null): ReportMetadataLike | null {
  return report?.metadata ?? null;
}

function formatRunLabel(run: ReportRunSummary): string {
  const timestamp = run.completedAt ?? run.createdAt;
  return new Date(timestamp).toLocaleString();
}

function ReportRunHistoryItem({
  run,
  selected,
  onSelect,
}: {
  run: ReportRunSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full rounded-lg border px-3 py-3 text-left transition-colors ${
        selected
          ? 'border-[var(--color-brand-accent)] bg-[var(--color-brand-accent)]/10'
          : 'border-[var(--border-default)] bg-[var(--bg-primary)] hover:border-[var(--border-focus)]'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-[var(--text-primary)]">{formatRunLabel(run)}</div>
          <div className="mt-1 text-xs text-[var(--text-secondary)]">
            {run.llmProvider && run.llmModel ? `${run.llmProvider} · ${run.llmModel}` : 'No model snapshot'}
          </div>
        </div>
        <VisibilityBadge visibility={run.visibility} compact />
      </div>
      <div className="mt-2 flex items-center justify-between text-[11px] text-[var(--text-muted)]">
        <span className="uppercase tracking-wide">{run.status.replaceAll('_', ' ')}</span>
        <span className="font-mono">{run.id.slice(0, 8)}</span>
      </div>
    </button>
  );
}

export default function ReportTab<TReport extends ReportPayloadLike>({
  appId,
  runId,
  supportsPdf = true,
  renderReport,
}: Props<TReport>) {
  const [configs, setConfigs] = useState<ReportConfigSummary[]>([]);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [reportRuns, setReportRuns] = useState<ReportRunSummary[]>([]);
  const [selectedReportRunId, setSelectedReportRunId] = useState<string | null>(null);
  const [report, setReport] = useState<TReport | null>(null);
  const [status, setStatus] = useState<Status>('loading');
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [savingVisibility, setSavingVisibility] = useState(false);
  const [showGenerateOverlay, setShowGenerateOverlay] = useState(false);
  const [progressMsg, setProgressMsg] = useState('');
  const [queuePosition, setQueuePosition] = useState<number | null>(null);
  const [jobPhase, setJobPhase] = useState<'queued' | 'running' | null>(null);
  const pollAbortRef = useRef<AbortController | null>(null);

  const [reportProvider, setReportProvider] = useState<LLMProvider>(LLM_PROVIDERS[0].value);
  const [reportModel, setReportModel] = useState('');
  const [newVisibility, setNewVisibility] = useState<AssetVisibility>('private');

  const geminiApiKey = useLLMSettingsStore((s) => s.geminiApiKey);
  const openaiApiKey = useLLMSettingsStore((s) => s.openaiApiKey);
  const azureApiKey = useLLMSettingsStore((s) => s.azureOpenaiApiKey);
  const azureEndpoint = useLLMSettingsStore((s) => s.azureOpenaiEndpoint);
  const anthropicApiKey = useLLMSettingsStore((s) => s.anthropicApiKey);
  const serviceAccountConfigured = useLLMSettingsStore((s) => s._serviceAccountConfigured);
  const canGenerate = usePermission('report:generate');
  const canExport = usePermission('evaluation:export');
  const canShare = usePermission('asset:share');

  const credentialsReady = hasProviderCredentials(reportProvider, {
    geminiApiKey,
    openaiApiKey,
    azureOpenaiApiKey: azureApiKey,
    azureOpenaiEndpoint: azureEndpoint,
    anthropicApiKey,
    _serviceAccountConfigured: serviceAccountConfigured,
  });

  const selectedConfig = useMemo(
    () => configs.find((config) => config.reportId === selectedReportId) ?? null,
    [configs, selectedReportId],
  );
  const selectedReportRun = useMemo(
    () => reportRuns.find((reportRun) => reportRun.id === selectedReportRunId) ?? null,
    [reportRuns, selectedReportRunId],
  );

  const loadConfigs = useCallback(async () => {
    const nextConfigs = await reportsApi.listReportConfigs(appId, 'single_run');
    setConfigs(nextConfigs);
    setSelectedReportId((current) => {
      if (current && nextConfigs.some((config) => config.reportId === current)) return current;
      return nextConfigs.find((config) => config.isDefault)?.reportId ?? nextConfigs[0]?.reportId ?? null;
    });
    return nextConfigs;
  }, [appId]);

  const loadReportRuns = useCallback(async (reportId: string) => {
    const nextRuns = await reportsApi.listReportRuns({
      appId,
      scope: 'single_run',
      sourceEvalRunId: runId,
      reportId,
      limit: 20,
    });
    setReportRuns(nextRuns);
    setSelectedReportRunId((current) => {
      if (current && nextRuns.some((reportRun) => reportRun.id === current)) return current;
      return nextRuns.find((reportRun) => reportRun.status === 'completed')?.id ?? nextRuns[0]?.id ?? null;
    });
    return nextRuns;
  }, [appId, runId]);

  const syncModelSelectionFromReport = useCallback((nextReport: TReport | null) => {
    const metadata = getReportMetadata(nextReport);
    if (metadata?.llmProvider) setReportProvider(metadata.llmProvider as LLMProvider);
    if (metadata?.llmModel) setReportModel(metadata.llmModel);
  }, []);

  const loadSelectedArtifact = useCallback(async (reportRun: ReportRunSummary | null) => {
    if (!reportRun) {
      setReport(null);
      setStatus('idle');
      return;
    }

    if (reportRun.status !== 'completed') {
      setReport(null);
      setStatus('generating');
      return;
    }

    const nextReport = await reportsApi.fetchReportRunArtifact(reportRun.id) as unknown as TReport;
    setReport(nextReport);
    syncModelSelectionFromReport(nextReport);
    setStatus('ready');
  }, [syncModelSelectionFromReport]);

  const handleJobProgress = useCallback((progress: JobProgress & { queuePosition?: number | null; status?: string }) => {
    const maybeStatus = progress.status;
    if (maybeStatus === 'queued') {
      setJobPhase('queued');
      setQueuePosition(progress.queuePosition ?? null);
      setProgressMsg('');
      return;
    }
    setJobPhase('running');
    setQueuePosition(null);
    setProgressMsg(progress.message || '');
  }, []);

  const pollExistingJob = useCallback(async (reportRun: ReportRunSummary) => {
    if (!reportRun.jobId) return;
    pollAbortRef.current?.abort();
    const controller = new AbortController();
    pollAbortRef.current = controller;
    setStatus('generating');

    try {
      await pollJobUntilComplete(reportRun.jobId, {
        pollIntervalMs: 2000,
        signal: controller.signal,
        onProgress: (progress) => {
          handleJobProgress(progress);
        },
      });
      const refreshedRuns = await loadReportRuns(reportRun.reportId);
      const completedRun = refreshedRuns.find((entry) => entry.id === reportRun.id && entry.status === 'completed')
        ?? refreshedRuns.find((entry) => entry.status === 'completed');
      if (completedRun) {
        setSelectedReportRunId(completedRun.id);
        await loadSelectedArtifact(completedRun);
      } else {
        setStatus('idle');
      }
    } catch (jobError) {
      if (jobError instanceof DOMException && jobError.name === 'AbortError') return;
      const message = jobError instanceof Error ? jobError.message : 'Report generation failed';
      setError(message);
      setStatus('error');
    } finally {
      setProgressMsg('');
      setQueuePosition(null);
      setJobPhase(null);
    }
  }, [handleJobProgress, loadReportRuns, loadSelectedArtifact]);

  useEffect(() => {
    let cancelled = false;
    setStatus('loading');
    setError(null);
    setReport(null);
    setReportRuns([]);
    setSelectedReportRunId(null);

    void loadConfigs()
      .then((nextConfigs) => {
        if (cancelled) return;
        if (nextConfigs.length === 0) {
          setStatus('idle');
        }
      })
      .catch((loadError) => {
        if (cancelled) return;
        setError(loadError instanceof Error ? loadError.message : 'Failed to load report configs');
        setStatus('error');
      });

    return () => {
      cancelled = true;
      pollAbortRef.current?.abort();
    };
  }, [loadConfigs, runId]);

  useEffect(() => {
    if (!selectedReportId) return;
    let cancelled = false;

    void loadReportRuns(selectedReportId)
      .then((nextRuns) => {
        if (cancelled) return;
        if (nextRuns.length === 0) {
          setReport(null);
          setStatus('idle');
        }
      })
      .catch((loadError) => {
        if (cancelled) return;
        setError(loadError instanceof Error ? loadError.message : 'Failed to load report runs');
        setStatus('error');
      });

    return () => {
      cancelled = true;
      pollAbortRef.current?.abort();
    };
  }, [loadReportRuns, selectedReportId]);

  useEffect(() => {
    if (!selectedReportRun) return;
    void loadSelectedArtifact(selectedReportRun).catch((loadError) => {
      const message = loadError instanceof Error ? loadError.message : 'Failed to load report';
      setError(message);
      setStatus('error');
    });
    if (selectedReportRun.status !== 'completed' && selectedReportRun.jobId) {
      void pollExistingJob(selectedReportRun);
    }
  }, [loadSelectedArtifact, pollExistingJob, selectedReportRun]);

  useEffect(() => {
    if (!selectedConfig) return;
    setNewVisibility(selectedConfig.defaultReportRunVisibility);
  }, [selectedConfig]);

  const handleGenerate = useCallback(async () => {
    if (!selectedConfig) return;
    setShowGenerateOverlay(false);
    setStatus('generating');
    setError(null);
    setProgressMsg('Submitting report job…');

    try {
      const completedJob = await submitAndPollJob(
        'generate-report',
        {
          run_id: runId,
          app_id: appId,
          report_id: selectedConfig.reportId,
          provider: reportProvider,
          model: reportModel || undefined,
          visibility: newVisibility,
        },
        {
          pollIntervalMs: 2000,
          onProgress: (progress) => {
            handleJobProgress(progress);
          },
        },
      );

      if (completedJob.status !== 'completed') {
        throw new Error(completedJob.errorMessage || 'Report generation failed');
      }

      const jobResult = (completedJob.result ?? {}) as Record<string, unknown>;
      const generatedReportRunId = typeof jobResult.report_run_id === 'string'
        ? jobResult.report_run_id
        : typeof jobResult.reportRunId === 'string'
          ? jobResult.reportRunId
          : null;

      const nextRuns = await loadReportRuns(selectedConfig.reportId);
      const nextReportRun = nextRuns.find((entry) => entry.id === generatedReportRunId)
        ?? nextRuns.find((entry) => entry.status === 'completed');

      if (!nextReportRun) {
        setReport(null);
        setStatus('idle');
        return;
      }

      setSelectedReportRunId(nextReportRun.id);
      await loadSelectedArtifact(nextReportRun);
      notificationService.success('Report generated');
    } catch (generateError) {
      const message = generateError instanceof Error ? generateError.message : 'Report generation failed';
      setError(message);
      setStatus('error');
      notificationService.error(message);
    } finally {
      setProgressMsg('');
      setQueuePosition(null);
      setJobPhase(null);
    }
  }, [
    appId,
    handleJobProgress,
    loadReportRuns,
    loadSelectedArtifact,
    newVisibility,
    reportModel,
    reportProvider,
    runId,
    selectedConfig,
  ]);

  const handleExportPdf = useCallback(async () => {
    if (!selectedReportRun || exporting) return;
    setExporting(true);
    try {
      const blob = await reportsApi.exportReportRunPdf(selectedReportRun.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `eval-report-${selectedReportRun.id.slice(0, 8)}.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
      notificationService.success('PDF exported');
    } catch (exportError) {
      notificationService.error(exportError instanceof Error ? exportError.message : 'PDF export failed');
    } finally {
      setExporting(false);
    }
  }, [exporting, selectedReportRun]);

  const handleReportRunVisibilityChange = useCallback(async (visibility: AssetVisibility) => {
    if (!selectedReportRun) return;
    setSavingVisibility(true);
    try {
      const updated = await reportsApi.updateReportRunVisibility(selectedReportRun.id, visibility);
      setReportRuns((current) => current.map((entry) => (entry.id === updated.id ? updated : entry)));
      notificationService.success('Visibility updated');
    } catch (visibilityError) {
      notificationService.error(visibilityError instanceof Error ? visibilityError.message : 'Failed to update visibility');
    } finally {
      setSavingVisibility(false);
    }
  }, [selectedReportRun]);

  const inProgressCard = (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-[var(--border-default)] py-10 px-6">
      {jobPhase === 'queued' ? (
        <Clock className="h-6 w-6 text-[var(--text-muted)]" />
      ) : (
        <Loader2 className="h-6 w-6 animate-spin text-[var(--color-info)]" />
      )}
      <p className="text-sm font-semibold text-[var(--text-primary)]">
        {jobPhase === 'queued' ? 'Queued' : 'Generating report'}
      </p>
      <p className="text-sm text-[var(--text-secondary)]">
        {jobPhase === 'queued'
          ? queuePosition != null && queuePosition > 0
            ? `${queuePosition} job${queuePosition > 1 ? 's' : ''} ahead`
            : 'Next in queue'
          : progressMsg || 'Composing the report and AI narrative.'}
      </p>
    </div>
  );

  if (status === 'loading') {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-[var(--text-muted)]" />
      </div>
    );
  }

  if (status === 'error' && !selectedConfig) {
    return (
      <EmptyState
        icon={FileBarChart}
        title="Report loading failed"
        description={error ?? 'Unable to load reporting surfaces.'}
        compact
      />
    );
  }

  const actionButtons = (
    <div className="flex items-center gap-2">
      {supportsPdf && canExport && selectedReportRun?.status === 'completed' ? (
        <Button size="sm" variant="secondary" onClick={() => void handleExportPdf()} disabled={exporting}>
          {exporting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
          {exporting ? 'Exporting…' : 'Export PDF'}
        </Button>
      ) : null}
      {canGenerate ? (
        <Button size="sm" onClick={() => setShowGenerateOverlay(true)}>
          <Sparkles className="h-3.5 w-3.5" />
          {selectedReportRun ? 'Generate new run' : 'Generate'}
        </Button>
      ) : null}
    </div>
  );

  return (
    <>
      <div className="grid gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="space-y-4">
          <section className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">Report Config</div>
            <div className="mt-3 space-y-2">
              {configs.map((config) => (
                <button
                  key={config.id}
                  type="button"
                  onClick={() => setSelectedReportId(config.reportId)}
                  className={`w-full rounded-lg border px-3 py-3 text-left transition-colors ${
                    config.reportId === selectedReportId
                      ? 'border-[var(--color-brand-accent)] bg-[var(--color-brand-accent)]/10'
                      : 'border-[var(--border-default)] bg-[var(--bg-primary)] hover:border-[var(--border-focus)]'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-[var(--text-primary)]">{config.name}</div>
                      {config.description ? (
                        <div className="mt-1 text-xs text-[var(--text-secondary)]">{config.description}</div>
                      ) : null}
                    </div>
                    <VisibilityBadge visibility={config.visibility} compact />
                  </div>
                </button>
              ))}
            </div>
          </section>

          <section className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4">
            <div className="flex items-center justify-between gap-2">
              <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">Report Runs</div>
              {selectedReportRun ? (
                <span className="text-[11px] text-[var(--text-muted)]">{reportRuns.length} total</span>
              ) : null}
            </div>
            <div className="mt-3 space-y-2">
              {reportRuns.length > 0 ? (
                reportRuns.map((reportRun) => (
                  <ReportRunHistoryItem
                    key={reportRun.id}
                    run={reportRun}
                    selected={reportRun.id === selectedReportRunId}
                    onSelect={() => setSelectedReportRunId(reportRun.id)}
                  />
                ))
              ) : (
                <div className="rounded-lg border border-dashed border-[var(--border-default)] px-3 py-6 text-center text-sm text-[var(--text-secondary)]">
                  No report runs yet.
                </div>
              )}
            </div>
          </section>
        </aside>

        <div className="space-y-4">
          {selectedReportRun ? (
            <section className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-[var(--text-primary)]">
                    {selectedConfig?.name ?? 'Report'}
                  </div>
                  <div className="mt-1 text-xs text-[var(--text-secondary)]">
                    {formatRunLabel(selectedReportRun)}
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <VisibilityBadge visibility={selectedReportRun.visibility} compact />
                </div>
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-4">
                <div>
                  <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-secondary)]">Visibility</div>
                  <VisibilityToggle
                    value={selectedReportRun.visibility}
                    onChange={(value) => void handleReportRunVisibilityChange(value)}
                    disabled={savingVisibility || !canShare}
                  />
                </div>
                {selectedReportRun.llmProvider && selectedReportRun.llmModel ? (
                  <div className="text-xs text-[var(--text-secondary)]">
                    Generated with <span className="font-medium text-[var(--text-primary)]">{selectedReportRun.llmProvider}</span> ·{' '}
                    <span className="font-medium text-[var(--text-primary)]">{selectedReportRun.llmModel}</span>
                  </div>
                ) : null}
              </div>
            </section>
          ) : (
            <div className="flex justify-end">{actionButtons}</div>
          )}

          {status === 'generating' && !report ? (
            <div className="min-h-[50vh] flex items-center justify-center">{inProgressCard}</div>
          ) : status === 'error' && !report ? (
            <EmptyState
              icon={FileBarChart}
              title="Report unavailable"
              description={error ?? 'Something went wrong while loading the selected report run.'}
              action={canGenerate ? { label: 'Generate', onClick: () => setShowGenerateOverlay(true) } : undefined}
            />
          ) : report ? (
            <div className="max-w-[980px]">{renderReport(report, actionButtons)}</div>
          ) : (
            <EmptyState
              icon={FileBarChart}
              title="No report generated yet"
              description="Choose a report config and generate a report run to view the composed report."
              action={canGenerate ? { label: 'Generate', onClick: () => setShowGenerateOverlay(true) } : undefined}
            />
          )}
        </div>
      </div>

      <Modal
        isOpen={showGenerateOverlay && canGenerate}
        onClose={() => setShowGenerateOverlay(false)}
        title="Generate Report"
        className="max-w-2xl"
      >
        <div className="space-y-5">
          <div className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4">
            <div className="text-sm font-semibold text-[var(--text-primary)]">{selectedConfig?.name ?? 'Report'}</div>
            {selectedConfig?.description ? (
              <p className="mt-1 text-sm text-[var(--text-secondary)]">{selectedConfig.description}</p>
            ) : null}
          </div>

          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">Provider and model</div>
            <LLMConfigSection
              provider={reportProvider}
              onProviderChange={(value) => {
                setReportProvider(value);
                setReportModel('');
              }}
              model={reportModel}
              onModelChange={setReportModel}
            />
          </div>

          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
              <Globe2 className="h-3.5 w-3.5" />
              Visibility
            </div>
            <VisibilityToggle value={newVisibility} onChange={setNewVisibility} disabled={!canShare} />
          </div>

          {!credentialsReady ? (
            <p className="text-sm text-[var(--color-warning)]">
              Configure provider credentials in Settings before generating a report.
            </p>
          ) : null}

          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setShowGenerateOverlay(false)}>
              Cancel
            </Button>
            <Button onClick={() => void handleGenerate()} disabled={!selectedConfig || !credentialsReady || !reportModel}>
              <Sparkles className="h-3.5 w-3.5" />
              Generate
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
