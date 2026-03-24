import { useState, useEffect, useCallback, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import { cn } from '@/utils';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ArrowLeft,
  Loader2,
  AlertTriangle,
  FileText,
  Trash2,
  XCircle,
  Phone,
  Search,
} from 'lucide-react';
import { Button, Tabs, EmptyState } from '@/components/ui';
import VerdictBadge from '@/features/evalRuns/components/VerdictBadge';
import { RunProgressBar } from '@/features/evalRuns/components/RunProgressBar';
import DistributionBar from '@/features/evalRuns/components/DistributionBar';
import { fetchEvalRun, fetchRunThreads, deleteEvalRun } from '@/services/api/evalRunsApi';
import { jobsApi } from '@/services/api/jobsApi';
import { notificationService } from '@/services/notifications';
import { usePoll } from '@/hooks';
import { routes } from '@/config/routes';
import { formatDuration } from '@/utils/formatters';
import { timeAgo } from '@/utils/evalFormatters';
import { isActiveStatus } from '@/utils/runStatus';
import type { EvalRun, ThreadEvalRow } from '@/types';
import type { Job } from '@/services/api/jobsApi';

/* ── Helpers ─────────────────────────────────────────────── */

function getRunName(run: EvalRun): string {
  const config = run.config as Record<string, unknown> | undefined;
  const summary = run.summary as Record<string, unknown> | undefined;
  return (
    (config?.run_name as string) ??
    (summary?.evaluator_name as string) ??
    (config?.evaluator_name as string) ??
    'Call Quality Evaluation'
  );
}

function getOverallScore(thread: ThreadEvalRow): number | null {
  const result = thread.result as unknown as Record<string, unknown> | undefined;
  if (!result) return null;
  // Score lives in evaluations[0].output.overall_score
  const evals = result.evaluations as Array<Record<string, unknown>> | undefined;
  if (evals && evals.length > 0) {
    const output = evals[0].output as Record<string, unknown> | undefined;
    if (output && typeof output.overall_score === 'number') return output.overall_score;
  }
  // Fallback: check top-level output
  const output = result.output as Record<string, unknown> | undefined;
  if (output && typeof output.overall_score === 'number') return output.overall_score;
  return null;
}

function getScoreBand(score: number | null): string {
  if (score === null) return 'Unknown';
  if (score >= 80) return 'Strong';
  if (score >= 65) return 'Good';
  if (score >= 50) return 'Needs work';
  return 'Poor';
}

function scoreColor(score: number | null): string {
  if (score === null) return 'var(--text-muted)';
  if (score >= 80) return 'var(--color-success)';
  if (score >= 65) return 'var(--color-warning)';
  return 'var(--color-error)';
}

/* ── Main Component ──────────────────────────────────────── */

export function InsideSalesRunDetail() {
  const { runId, callId } = useParams<{ runId: string; callId?: string }>();
  const navigate = useNavigate();
  const [run, setRun] = useState<EvalRun | null>(null);
  const [threads, setThreads] = useState<ThreadEvalRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const fetchData = useCallback(async () => {
    if (!runId) return;
    try {
      const [runData, threadData] = await Promise.all([
        fetchEvalRun(runId),
        fetchRunThreads(runId),
      ]);
      setRun(runData);
      setThreads(threadData.evaluations);
      setError(null);

      // Fetch active job if running
      if (isActiveStatus(runData.status) && runData.jobId) {
        const job = await jobsApi.get(runData.jobId);
        setActiveJob(job);
      } else {
        setActiveJob(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load run');
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Poll while active
  const isActive = run ? isActiveStatus(run.status) : false;
  usePoll({ fn: async () => { await fetchData(); return true; }, enabled: isActive, intervalMs: 3000 });

  const elapsed = useMemo(() => {
    if (!run?.startedAt) return '';
    const ms = Date.now() - new Date(run.startedAt).getTime();
    return formatDuration(Math.floor(ms / 1000));
  }, [run?.startedAt]);

  const handleDelete = useCallback(async () => {
    if (!run) return;
    setIsDeleting(true);
    try {
      await deleteEvalRun(run.id);
      notificationService.success('Run deleted');
      navigate(routes.insideSales.runs);
    } catch {
      notificationService.error('Delete failed');
    } finally {
      setIsDeleting(false);
    }
  }, [run, navigate]);

  const handleCancel = useCallback(async () => {
    if (!run?.jobId) return;
    setCancelling(true);
    try {
      await jobsApi.cancel(run.jobId);
      notificationService.success('Run cancelled');
      fetchData();
    } catch {
      notificationService.error('Cancel failed');
    } finally {
      setCancelling(false);
    }
  }, [run, fetchData]);

  // Must be above early returns — Rules of Hooks
  const filteredThreads = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return threads;
    return threads.filter((t) => {
      const meta = (t.result as unknown as Record<string, unknown>)?.call_metadata as Record<string, unknown> | undefined;
      const agent = (meta?.agent as string) || '';
      const lead = (meta?.lead as string) || '';
      return agent.toLowerCase().includes(q) || lead.toLowerCase().includes(q) || t.thread_id.includes(q);
    });
  }, [threads, searchQuery]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-5 w-5 animate-spin text-[var(--text-muted)]" />
      </div>
    );
  }

  if (error || !run) {
    return (
      <div className="space-y-3">
        <Link to={routes.insideSales.runs} className="inline-flex items-center gap-1 text-sm text-[var(--text-muted)] hover:text-[var(--text-brand)]">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Runs
        </Link>
        <div className="bg-[var(--surface-error)] border border-[var(--border-error)] rounded p-3 text-sm text-[var(--color-error)] flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {error || 'Run not found'}
        </div>
      </div>
    );
  }

  // Compute stats from threads
  const evaluated = threads.filter((t) => t.success_status).length;
  const failed = threads.length - evaluated;
  const scores = threads.map(getOverallScore).filter((s): s is number => s !== null);
  const avgScore = scores.length > 0 ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null;

  const scoreBands: Record<string, number> = { Strong: 0, Good: 0, 'Needs work': 0, Poor: 0 };
  scores.forEach((s) => { scoreBands[getScoreBand(s)]++; });

  const resultsTab = {
    id: 'results',
    label: `Results (${threads.length})`,
    content: (
      <div className="space-y-4 py-2">
        {/* Stat cards */}
        <div className="grid grid-cols-3 gap-3">
          <StatCard label="Calls Evaluated" value={`${evaluated} / ${threads.length}`} />
          <StatCard label="Avg Score" value={avgScore !== null ? `${avgScore} / 100` : '—'} color={scoreColor(avgScore)} />
          <StatCard label="Failed" value={String(failed)} color={failed > 0 ? 'var(--color-error)' : 'var(--text-muted)'} />
        </div>

        {/* Distribution */}
        {scores.length > 0 && (
          <div className="grid grid-cols-2 gap-3">
            <div>
              <h4 className="text-[10px] font-medium text-[var(--text-muted)] uppercase mb-1.5">Score Bands</h4>
              <DistributionBar
                distribution={scoreBands}
                order={['Strong', 'Good', 'Needs work', 'Poor'] as const}
              />
            </div>
          </div>
        )}

        {/* Search */}
        <div className="relative max-w-sm">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--text-muted)]" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search agent, lead..."
            className="w-full pl-8 pr-3 py-1.5 text-xs rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)]"
          />
        </div>

        {/* Call results table */}
        {filteredThreads.length === 0 && isActive ? (
          <div className="flex flex-col items-center gap-2 border border-dashed border-[var(--border-default)] rounded-lg py-10 px-6">
            <Loader2 className="h-6 w-6 text-[var(--color-info)] animate-spin" />
            <p className="text-sm font-semibold text-[var(--text-primary)]">Evaluations are being processed...</p>
            <p className="text-sm text-[var(--text-secondary)]">Results will appear here as calls are evaluated.</p>
          </div>
        ) : filteredThreads.length === 0 ? (
          <EmptyState icon={Phone} title="No results" description="No evaluated calls found." compact />
        ) : (
          <div className="rounded-md border border-[var(--border-default)] overflow-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-[var(--bg-secondary)] z-10">
                <tr className="border-b border-[var(--border-default)]">
                  <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Agent → Lead</th>
                  <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Duration</th>
                  <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Score</th>
                  <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Band</th>
                  <th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredThreads.map((t) => {
                  const score = getOverallScore(t);
                  const meta = (t.result as unknown as Record<string, unknown>)?.call_metadata as Record<string, unknown> | undefined;
                  const agent = (meta?.agent as string) || '—';
                  const lead = (meta?.lead as string) || '—';
                  const duration = (meta?.duration as number) || 0;
                  return (
                    <tr
                      key={t.id}
                      onClick={() => navigate(`/inside-sales/runs/${run.id}/calls/${t.thread_id}`)}
                      className="border-b border-[var(--border-subtle)] cursor-pointer hover:bg-[var(--interactive-secondary)] transition-colors"
                    >
                      <td className="px-3 py-2.5 text-[var(--text-primary)]">
                        {agent} <span className="text-[var(--text-muted)]">→</span> {lead}
                      </td>
                      <td className="px-3 py-2.5 text-[var(--text-secondary)]">
                        {duration > 0 ? formatDuration(duration) : '—'}
                      </td>
                      <td className="px-3 py-2.5 font-bold" style={{ color: scoreColor(score) }}>
                        {score !== null ? score : '—'}
                      </td>
                      <td className="px-3 py-2.5">
                        <VerdictBadge verdict={getScoreBand(score)} category="status" />
                      </td>
                      <td className="px-3 py-2.5">
                        {t.success_status ? (
                          <span className="text-[var(--color-success)]">✓</span>
                        ) : (
                          <span className="text-[var(--color-error)]">✗</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    ),
  };

  const reportTab = {
    id: 'report',
    label: 'Report',
    content: (
      <div className="flex items-center justify-center py-16">
        <EmptyState
          icon={FileText}
          title="Reports coming soon"
          description="Report generation for inside-sales will be available in a future update."
          compact
        />
      </div>
    ),
  };

  // If callId is present, show call eval detail instead of run overview
  const selectedThread = callId ? threads.find((t) => t.thread_id === callId) : null;

  if (callId && selectedThread) {
    return <CallEvalDetail run={run} thread={selectedThread} siblings={threads} />;
  }

  return (
    <div className="space-y-4">
      {/* Breadcrumb */}
      <div className="flex items-center gap-1.5 text-sm text-[var(--text-muted)]">
        <Link to={routes.insideSales.runs} className="hover:text-[var(--text-brand)]">Runs</Link>
        <span>/</span>
        <span className="font-mono text-[var(--text-secondary)]">{run.id.slice(0, 12)}</span>
      </div>

      {/* Header */}
      <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-md px-4 py-2.5">
        <div className="flex items-center gap-2">
          <h1 className="text-[13px] font-bold text-[var(--text-primary)] truncate">{getRunName(run)}</h1>
          <VerdictBadge verdict={run.status} category="status" />
          <div className="ml-auto flex items-center gap-2">
            <Link
              to={`${routes.insideSales.logs}?run_id=${run.id}`}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] rounded transition-colors"
            >
              <FileText className="h-3 w-3" />
              Logs
            </Link>
            {isActive && (
              <Button variant="ghost" size="sm" onClick={handleCancel} disabled={cancelling}>
                <XCircle className="h-3.5 w-3.5" />
                {cancelling ? 'Cancelling...' : 'Cancel'}
              </Button>
            )}
            <Button variant="danger" size="sm" onClick={handleDelete} disabled={isDeleting}>
              <Trash2 className="h-3.5 w-3.5" />
              Delete
            </Button>
          </div>
        </div>
        <div className="flex items-center gap-3 mt-1 text-[11px] text-[var(--text-muted)]">
          <span className="font-mono">{run.id.slice(0, 8)}</span>
          {run.startedAt && <span>{timeAgo(run.startedAt)}</span>}
          {run.durationMs && <span>{formatDuration(Math.round(run.durationMs / 1000))}</span>}
          {run.llmModel && <span>{run.llmModel}</span>}
        </div>
      </div>

      {/* Progress bar */}
      {isActive && <RunProgressBar job={activeJob} elapsed={elapsed} />}

      {/* Tabs */}
      <Tabs tabs={[resultsTab, reportTab]} defaultTab="results" />
    </div>
  );
}

/* ── StatCard ────────────────────────────────────────────── */

function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2.5">
      <div className="text-[10px] font-medium text-[var(--text-muted)] uppercase">{label}</div>
      <div className="text-lg font-bold mt-0.5" style={{ color: color || 'var(--text-primary)' }}>
        {value}
      </div>
    </div>
  );
}

/* ── Call Eval Detail (split-pane, mirrors ThreadDetailV2 layout) ── */

function CallEvalDetail({
  run,
  thread,
  siblings,
}: {
  run: EvalRun;
  thread: ThreadEvalRow;
  siblings: ThreadEvalRow[];
}) {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'scorecard' | 'compliance'>('scorecard');

  const result = thread.result as unknown as Record<string, unknown> | undefined;
  const meta = result?.call_metadata as Record<string, unknown> | undefined;
  const evals = result?.evaluations as Array<Record<string, unknown>> | undefined;
  const evalOutput = evals?.[0]?.output as Record<string, unknown> | undefined;
  const reasoning = evalOutput?.reasoning as string | undefined;
  const overallScore = getOverallScore(thread);
  const transcript = result?.transcript as string | undefined;

  // Dimension scores (numeric fields, excluding overall_score and reasoning)
  const dimensions = evalOutput
    ? Object.entries(evalOutput).filter(
        ([k, v]) => typeof v === 'number' && k !== 'overall_score'
      )
    : [];

  // Compliance gates (boolean fields)
  const complianceGates = evalOutput
    ? Object.entries(evalOutput).filter(([, v]) => typeof v === 'boolean')
    : [];

  const allPassed = complianceGates.every(([, v]) => v === true);

  // Thread navigation
  const currentIdx = siblings.findIndex((s) => s.thread_id === thread.thread_id);
  const prevThread = currentIdx > 0 ? siblings[currentIdx - 1] : null;
  const nextThread = currentIdx < siblings.length - 1 ? siblings[currentIdx + 1] : null;
  const goToThread = (id: string) => navigate(`/inside-sales/runs/${run.id}/calls/${id}`);

  return (
    <div className="flex flex-col h-[calc(100vh-var(--header-height,48px))]">
      {/* Header */}
      <div className="shrink-0 pb-3 space-y-2">
        {/* Row 1: breadcrumb + thread nav */}
        <div className="flex items-center justify-between gap-4">
          <nav className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] min-w-0">
            <Link to={routes.insideSales.runs} className="hover:text-[var(--text-brand)] shrink-0">Runs</Link>
            <span>/</span>
            <button
              onClick={() => navigate(routes.insideSales.runDetail(run.id))}
              className="hover:text-[var(--text-brand)] font-mono shrink-0"
            >
              {run.id.slice(0, 12)}
            </button>
            <span>/</span>
            <span className="font-mono text-[var(--text-primary)] font-medium truncate">
              {(meta?.agent as string) || '—'} → {(meta?.lead as string) || '—'}
            </span>
          </nav>

          {/* Thread navigation */}
          {siblings.length > 1 && (
            <span className="inline-flex items-center gap-0.5 border border-[var(--border-subtle)] rounded-md bg-[var(--bg-secondary)] shrink-0">
              <button
                disabled={!prevThread}
                onClick={() => prevThread && goToThread(prevThread.thread_id)}
                className="p-1 disabled:opacity-30 hover:bg-[var(--interactive-secondary)] rounded-l-md transition-colors cursor-pointer disabled:cursor-default"
              >
                <ArrowLeft size={14} />
              </button>
              <span className="text-[10px] tabular-nums px-1 border-x border-[var(--border-subtle)]">
                {currentIdx + 1}/{siblings.length}
              </span>
              <button
                disabled={!nextThread}
                onClick={() => nextThread && goToThread(nextThread.thread_id)}
                className="p-1 disabled:opacity-30 hover:bg-[var(--interactive-secondary)] rounded-r-md transition-colors cursor-pointer disabled:cursor-default"
              >
                <ArrowLeft size={14} className="rotate-180" />
              </button>
            </span>
          )}
        </div>

        {/* Row 2: summary bar */}
        <div className="overflow-x-auto scrollbar-thin">
          <div className="w-fit mx-auto">
            <div className="inline-flex items-stretch rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-sm">
              <SummaryPill label="Score" value={overallScore !== null ? `${overallScore}/100` : '—'} color={scoreColor(overallScore)} />
              <SummaryPill label="Verdict" value={getScoreBand(overallScore)} color={scoreColor(overallScore)} />
              <SummaryPill
                label="Compliance"
                value={complianceGates.length > 0 ? (allPassed ? 'Pass' : 'Fail') : '—'}
                color={complianceGates.length > 0 ? (allPassed ? 'var(--color-success)' : 'var(--color-error)') : undefined}
              />
              <SummaryPill label="Agent" value={(meta?.agent as string) || '—'} />
              <SummaryPill label="Duration" value={typeof meta?.duration === 'number' ? formatDuration(meta.duration) : '—'} />
            </div>
          </div>
        </div>
      </div>

      {/* Split pane: transcript left, scorecard/compliance right */}
      <div className="hidden md:flex flex-1 min-h-0">
        {/* Left: transcript */}
        <div className="w-[35%] min-w-[280px] max-w-[420px] flex flex-col min-h-0 border-r border-[var(--border-subtle)]">
          <div className="px-3 py-2 border-b border-[var(--border-subtle)] text-xs font-semibold text-[var(--text-muted)] uppercase">
            Transcript
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto px-3 py-2">
            {transcript ? (
              <div className="text-xs text-[var(--text-secondary)] whitespace-pre-wrap leading-relaxed font-mono">
                {transcript}
              </div>
            ) : (
              <p className="text-xs text-[var(--text-muted)] py-4 text-center">No transcript available.</p>
            )}
          </div>
        </div>

        {/* Right: tabs */}
        <div className="flex-1 min-w-0 flex flex-col min-h-0">
          {/* Tab bar */}
          <div className="flex border-b border-[var(--border-subtle)]">
            {(['scorecard', 'compliance'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={cn(
                  'px-4 py-2 text-xs font-semibold transition-colors border-b-2',
                  activeTab === tab
                    ? 'border-[var(--interactive-primary)] text-[var(--text-brand)]'
                    : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                )}
              >
                {tab === 'scorecard' ? 'Scorecard' : 'Compliance'}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3">
            {activeTab === 'scorecard' && (
              <div className="space-y-0">
                {dimensions.map(([key, val]) => {
                  const label = key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
                  const score = val as number;
                  const pctVal = Math.min(100, Math.max(0, score * 100 / (score <= 15 ? 15 : 100)));
                  return (
                    <div key={key} className="flex items-center gap-2 py-2 border-b border-[var(--border-subtle)] last:border-b-0">
                      <span className="text-xs text-[var(--text-primary)] w-[45%] shrink-0">{label}</span>
                      <div className="flex-1 h-2 rounded-full bg-[var(--bg-tertiary)] overflow-hidden">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${pctVal}%`,
                            background: score >= 8 ? 'var(--color-success)' : score >= 5 ? 'var(--color-warning)' : 'var(--color-error)',
                          }}
                        />
                      </div>
                      <span className="text-xs font-bold w-12 text-right" style={{ color: scoreColor(score) }}>
                        {score}
                      </span>
                    </div>
                  );
                })}
                {/* Total row */}
                {overallScore !== null && (
                  <div className="flex items-center justify-between mt-3 px-3 py-2.5 bg-[var(--bg-secondary)] rounded-md border border-[var(--border-subtle)]">
                    <span className="text-[13px] font-semibold text-[var(--text-primary)]">Total</span>
                    <span className="text-lg font-bold" style={{ color: scoreColor(overallScore) }}>
                      {overallScore}/100
                    </span>
                  </div>
                )}
                {/* Reasoning */}
                {reasoning && (
                  <div className="mt-4 pt-3 border-t border-[var(--border-subtle)]">
                    <h4 className="text-xs font-semibold text-[var(--text-muted)] uppercase mb-2">Reasoning</h4>
                    <div className="text-xs text-[var(--text-secondary)] leading-relaxed prose prose-sm prose-invert max-w-none [&_strong]:text-[var(--text-primary)] [&_p]:mb-2 [&_ol]:pl-4 [&_li]:mb-1">
                      <ReactMarkdown>{reasoning}</ReactMarkdown>
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'compliance' && (
              <div>
                {/* Filter chips */}
                <div className="flex flex-wrap gap-1 pb-3">
                  <span className="px-2 py-0.5 text-xs rounded-full border border-[var(--border-brand)] bg-[var(--surface-info)] text-[var(--text-brand)]">
                    All ({complianceGates.length})
                  </span>
                  <span className="px-2 py-0.5 text-xs rounded-full border border-[var(--border-subtle)] text-[var(--text-secondary)]">
                    Violations ({complianceGates.filter(([, v]) => !v).length})
                  </span>
                  <span className="px-2 py-0.5 text-xs rounded-full border border-[var(--border-subtle)] text-[var(--text-secondary)]">
                    Passed ({complianceGates.filter(([, v]) => v).length})
                  </span>
                </div>
                {/* Compliance table */}
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-[var(--border-subtle)]">
                      <th className="text-center w-12 py-1.5 px-2 font-semibold text-[var(--text-muted)]">Status</th>
                      <th className="text-left py-1.5 px-2 font-semibold text-[var(--text-muted)]">Rule</th>
                    </tr>
                  </thead>
                  <tbody>
                    {complianceGates.map(([key, val]) => {
                      const label = key.replace(/^compliance_/, '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
                      const passed = val as boolean;
                      return (
                        <tr key={key} className="border-b border-[var(--border-subtle)]">
                          <td className="text-center py-2 px-2">
                            <span className={cn(
                              'inline-flex items-center justify-center w-5 h-5 rounded-full text-[11px] font-bold',
                              passed ? 'bg-green-500/15 text-green-400' : 'bg-red-500/15 text-red-400'
                            )}>
                              {passed ? '✓' : '✗'}
                            </span>
                          </td>
                          <td className="py-2 px-2">
                            <span className={cn(
                              'text-[13px] font-semibold',
                              passed ? 'text-[var(--color-success)]' : 'text-[var(--color-error)]'
                            )}>
                              {label}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Mobile: stacked */}
      <div className="flex flex-col flex-1 min-h-0 md:hidden space-y-3 overflow-y-auto">
        {transcript && (
          <details className="shrink-0">
            <summary className="text-xs text-[var(--text-muted)] font-medium cursor-pointer py-1.5 px-1">
              Transcript
            </summary>
            <div className="max-h-[300px] overflow-y-auto px-2 py-1">
              <div className="text-xs text-[var(--text-secondary)] whitespace-pre-wrap leading-relaxed font-mono">
                {transcript}
              </div>
            </div>
          </details>
        )}
        {dimensions.length > 0 && (
          <div className="px-2">
            {dimensions.map(([key, val]) => {
              const label = key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
              const score = val as number;
              return (
                <div key={key} className="flex items-center justify-between py-1.5 border-b border-[var(--border-subtle)] text-xs">
                  <span className="text-[var(--text-secondary)]">{label}</span>
                  <span className="font-bold" style={{ color: scoreColor(score) }}>{score}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Summary Pill ───────────────────────────────────────── */

function SummaryPill({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-0.5 px-4 py-2 border-l border-[var(--border-subtle)] first:border-l-0">
      <span className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] leading-none">{label}</span>
      <span className="leading-none font-semibold text-sm" style={{ color: color || 'var(--text-primary)' }}>{value}</span>
    </div>
  );
}
