import { useState, useCallback, useEffect, useRef } from 'react';
import { Loader2, RefreshCw, Download, FileBarChart, Sparkles, X, Clock } from 'lucide-react';
import type { ReportPayload } from '@/types/reports';
import type { LLMProvider } from '@/types';
import { reportsApi } from '@/services/api/reportsApi';
import { jobsApi, type Job } from '@/services/api/jobsApi';
import { poll } from '@/services/api/jobPolling';
import { notificationService } from '@/services/notifications';
import { EmptyState, Button, LLMConfigSection } from '@/components/ui';
import { useLLMSettingsStore, hasProviderCredentials, LLM_PROVIDERS } from '@/stores';

interface Props {
  runId: string;
  /** Renderer for the report content. Receives the raw report payload (any shape). */
  renderReport: (report: unknown) => React.ReactNode;
}

type Status = 'loading' | 'idle' | 'generating' | 'ready' | 'error';

export default function ReportTab({ runId, renderReport }: Props) {
  const [report, setReport] = useState<ReportPayload | null>(null);
  const [status, setStatus] = useState<Status>('loading');
  const [refreshing, setRefreshing] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progressMsg, setProgressMsg] = useState('');
  const [showRefreshSelector, setShowRefreshSelector] = useState(false);
  const refreshPopoverRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Close popover on outside click
  useEffect(() => {
    if (!showRefreshSelector) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (refreshPopoverRef.current && !refreshPopoverRef.current.contains(e.target as Node)) {
        setShowRefreshSelector(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showRefreshSelector]);

  // Model selection for narrative generation
  const [reportProvider, setReportProvider] = useState<LLMProvider>('gemini');
  const [reportModel, setReportModel] = useState('');

  // Credential check for generate button gating
  const geminiApiKey = useLLMSettingsStore((s) => s.geminiApiKey);
  const openaiApiKey = useLLMSettingsStore((s) => s.openaiApiKey);
  const azureApiKey = useLLMSettingsStore((s) => s.azureOpenaiApiKey);
  const azureEndpoint = useLLMSettingsStore((s) => s.azureOpenaiEndpoint);
  const anthropicApiKey = useLLMSettingsStore((s) => s.anthropicApiKey);
  const saConfigured = useLLMSettingsStore((s) => s._serviceAccountConfigured);

  const storeSlice = { geminiApiKey, openaiApiKey, azureOpenaiApiKey: azureApiKey, azureOpenaiEndpoint: azureEndpoint, anthropicApiKey, _serviceAccountConfigured: saConfigured };
  const credentialsReady = hasProviderCredentials(reportProvider, storeSlice);

  const [queuePosition, setQueuePosition] = useState<number | null>(null);
  const [jobPhase, setJobPhase] = useState<'queued' | 'running' | null>(null);

  // ── Poll a job until done, then load the cached report ──
  const pollAndLoad = useCallback(async (jobId: string, isRefresh: boolean) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const finalJob = await poll<Job>({
        fn: async () => {
          const job = await jobsApi.get(jobId);

          // Track queue vs running phase for UI differentiation
          if (job.status === 'queued') {
            setJobPhase('queued');
            setQueuePosition(job.queuePosition ?? null);
            setProgressMsg('');
          } else if (job.status === 'running') {
            setJobPhase('running');
            setQueuePosition(null);
            setProgressMsg(job.progress?.message || '');
          }

          if (['completed', 'failed', 'cancelled'].includes(job.status)) {
            return { done: true, data: job };
          }
          return { done: false };
        },
        intervalMs: 5000,
        signal: controller.signal,
      });

      if (finalJob?.status === 'completed') {
        const data = await reportsApi.fetchReport(runId, { cacheOnly: true });
        setReport(data);
        setStatus('ready');
        // Sync the provider/model selectors to match the report that was just
        // generated so the header bar and refresh popover show the correct values.
        if (data.metadata?.llmProvider) {
          setReportProvider(data.metadata.llmProvider as LLMProvider);
        }
        if (data.metadata?.llmModel) {
          setReportModel(data.metadata.llmModel);
        }
        const hasNarrative = finalJob.result?.has_narrative !== false;
        if (!hasNarrative) {
          notificationService.warning('Report ready, but AI narrative could not be generated');
        } else if (isRefresh) {
          notificationService.success('Report regenerated');
        }
      } else if (finalJob?.status === 'failed') {
        const msg = finalJob.errorMessage || 'Report generation failed';
        setError(msg);
        if (!isRefresh) setStatus('error');
        else notificationService.error(msg);
      } else if (finalJob?.status === 'cancelled') {
        setStatus('idle');
        notificationService.warning('Report generation was cancelled');
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === 'AbortError') return;
      const msg = e instanceof Error ? e.message : 'Report generation failed';
      setError(msg);
      if (!isRefresh) setStatus('error');
      else notificationService.error(msg);
    } finally {
      setRefreshing(false);
      setProgressMsg('');
      setQueuePosition(null);
      setJobPhase(null);
    }
  }, [runId]);

  // ── On mount: check running jobs first (survives refresh), then cache, then idle ──
  useEffect(() => {
    setReportProvider(LLM_PROVIDERS[0].value);
    setReportModel('');

    let cancelled = false;

    (async () => {
      // 1. Check for an in-progress generate-report job for this run FIRST.
      //    This ensures a page refresh during generation resumes polling
      //    instead of showing a stale cached report.
      try {
        const jobs = await jobsApi.list({ jobType: 'generate-report' });
        const active = jobs.find(
          (j) => ['queued', 'running'].includes(j.status) &&
            (j.params as Record<string, unknown>)?.run_id === runId,
        );
        if (active && !cancelled) {
          setStatus('generating');
          pollAndLoad(active.id, false);
          return;
        }
      } catch { /* ignore */ }

      if (cancelled) return;

      // 2. No active job — check for cached report
      try {
        const data = await reportsApi.fetchReport(runId, { cacheOnly: true });
        if (!cancelled) {
          setReport(data);
          setStatus('ready');
          // Sync selectors to match the cached report's provider/model
          if (data.metadata?.llmProvider) {
            setReportProvider(data.metadata.llmProvider as LLMProvider);
          }
          if (data.metadata?.llmModel) {
            setReportModel(data.metadata.llmModel);
          }
        }
        return;
      } catch { /* no cache */ }

      if (!cancelled) setStatus('idle');
    })();

    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
  }, [runId, pollAndLoad]);

  // ── Submit a generate-report job ──
  const generateReport = useCallback(async (refresh = false) => {
    if (refresh && report) {
      setRefreshing(true);
    } else {
      setStatus('generating');
    }
    setError(null);
    setProgressMsg('Submitting report job…');

    try {
      const job = await jobsApi.submit('generate-report', {
        run_id: runId,
        refresh,
        provider: reportProvider,
        model: reportModel || undefined,
      });
      await pollAndLoad(job.id, refresh);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to submit report job';
      setError(msg);
      if (!report) setStatus('error');
      else notificationService.error(msg);
      setRefreshing(false);
    }
  }, [runId, report, reportProvider, reportModel, pollAndLoad]);

  const handleExportPdf = useCallback(async () => {
    if (exporting) return;
    setExporting(true);
    try {
      const blob = await reportsApi.exportPdf(runId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `eval-report-${runId.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      notificationService.success('PDF exported');
    } catch (e: unknown) {
      notificationService.error(e instanceof Error ? e.message : 'PDF export failed');
    } finally {
      setExporting(false);
    }
  }, [runId, exporting]);

  // ── Shared in-progress card (matches RunDetail eval-in-progress pattern) ──
  const inProgressCard = (label: string) => {
    const isQueued = jobPhase === 'queued';
    return (
      <div className="flex flex-col items-center gap-2 border border-dashed border-[var(--border-default)] rounded-lg py-10 px-6">
        {isQueued ? (
          <Clock className="h-6 w-6 text-[var(--text-muted)]" />
        ) : (
          <Loader2 className="h-6 w-6 text-[var(--color-info)] animate-spin" />
        )}
        <p className="text-sm font-semibold text-[var(--text-primary)]">
          {isQueued ? 'Queued' : label}
        </p>
        <p className="text-sm text-[var(--text-secondary)]">
          {isQueued
            ? `${queuePosition != null && queuePosition > 0 ? `${queuePosition} job${queuePosition > 1 ? 's' : ''} ahead` : 'Next in queue'}`
            : progressMsg || 'Aggregating evaluation data and generating AI narrative. This typically takes 10\u201330 seconds.'}
        </p>
      </div>
    );
  };

  // ── Loading: checking for cached report ──
  if (status === 'loading') {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Loader2 className="h-5 w-5 text-[var(--text-muted)] animate-spin" />
      </div>
    );
  }

  // ── Idle: no report generated yet ──
  if (status === 'idle') {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="max-w-[500px] w-full px-4">
          <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-secondary)] p-6 space-y-5">
            {/* Header */}
            <div className="text-center space-y-1.5">
              <div className="inline-flex items-center justify-center w-10 h-10 rounded-lg bg-[var(--color-brand-accent)]/10 mb-1">
                <FileBarChart className="h-5 w-5 text-[var(--text-brand)]" />
              </div>
              <h3 className="text-lg font-semibold text-[var(--text-primary)]">Evaluation Report</h3>
              <p className="text-sm text-[var(--text-secondary)]">
                Generate an aggregate report with health scores, verdict distributions, rule compliance, exemplar threads, and AI-powered recommendations.
              </p>
            </div>

            {/* Model selector */}
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">
                <Sparkles className="h-3.5 w-3.5" />
                Narrative Model
              </div>

              <LLMConfigSection
                provider={reportProvider}
                onProviderChange={(v) => { setReportProvider(v); setReportModel(''); }}
                model={reportModel}
                onModelChange={setReportModel}
              />
            </div>

            {/* Generate button */}
            <Button
              variant="primary"
              size="lg"
              icon={FileBarChart}
              onClick={() => generateReport()}
              disabled={!credentialsReady || !reportModel}
              className="w-full"
            >
              Generate Report
            </Button>

            {!credentialsReady && (
              <p className="text-xs text-center text-[var(--color-warning)]">
                Configure LLM credentials in Settings to generate reports.
              </p>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ── Generating: first-time load ──
  if (status === 'generating' && !report) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center px-4">
        {inProgressCard('Generating report...')}
      </div>
    );
  }

  // ── Error: no report to show ──
  if (status === 'error' && !report) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="max-w-[900px] w-full px-4">
          <EmptyState
            icon={FileBarChart}
            title="Report generation failed"
            description={error ?? 'Something went wrong. Try again.'}
            action={{
              label: 'Retry',
              onClick: () => generateReport(),
            }}
          />
        </div>
      </div>
    );
  }

  if (!report) return null;

  // ── Generic action bar: refresh + PDF export (shared by all report views) ──
  const actionBar = (
    <div className="report-actions flex items-center justify-end gap-2 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-subtle)] px-4 py-2 mb-4">
      <button
        onClick={handleExportPdf}
        disabled={refreshing || exporting}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-[var(--interactive-primary)] rounded-md hover:opacity-90 transition-colors disabled:opacity-50"
      >
        {exporting ? (
          <Loader2 className="h-3 w-3 animate-spin" />
        ) : (
          <Download className="h-3 w-3" />
        )}
        {exporting ? 'Exporting...' : 'Export PDF'}
      </button>
      <div className="relative" ref={refreshPopoverRef}>
        <button
          onClick={() => setShowRefreshSelector((v) => !v)}
          disabled={refreshing}
          className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-[var(--text-secondary)] bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-md hover:bg-[var(--bg-tertiary)] transition-colors disabled:opacity-50"
          title="Regenerate report (bypasses cache)"
        >
          <RefreshCw className={`h-3 w-3 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>

        {showRefreshSelector && (
          <div className="absolute right-0 top-full mt-2 w-72 rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] shadow-lg z-20 p-3 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-[11px] font-medium text-[var(--text-secondary)] uppercase tracking-wider">
                <Sparkles className="h-3 w-3" />
                Narrative Model
              </div>
              <button
                onClick={() => setShowRefreshSelector(false)}
                className="p-0.5 rounded hover:bg-[var(--bg-tertiary)] text-[var(--text-muted)]"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>

            <LLMConfigSection
              provider={reportProvider}
              onProviderChange={(v) => { setReportProvider(v); setReportModel(''); }}
              model={reportModel}
              onModelChange={setReportModel}
              compact
            />

            <button
              onClick={() => {
                setShowRefreshSelector(false);
                generateReport(true);
              }}
              disabled={!credentialsReady || !reportModel}
              className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium text-white bg-[var(--interactive-primary)] rounded-md hover:opacity-90 transition-colors disabled:opacity-50"
            >
              <RefreshCw className="h-3 w-3" />
              Regenerate Report
            </button>
          </div>
        )}
      </div>
    </div>
  );

  // ── Ready state: action bar + custom content ──
  return (
    <div className="max-w-[900px] mx-auto pb-8">
      {actionBar}
      {refreshing ? (
        <div className="flex items-center justify-center py-20">
          {inProgressCard('Regenerating report...')}
        </div>
      ) : (
        renderReport(report)
      )}
    </div>
  );
}
