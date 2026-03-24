import { useState, useEffect, useCallback, useMemo } from 'react';
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
  const output = (thread.result as unknown as Record<string, unknown>)?.output as Record<string, unknown> | undefined;
  if (!output) return null;
  const score = output.overall_score;
  return typeof score === 'number' ? score : null;
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
  const { runId } = useParams<{ runId: string }>();
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
        {filteredThreads.length === 0 ? (
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
