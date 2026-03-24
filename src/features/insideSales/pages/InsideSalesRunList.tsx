import { useState, useEffect, useCallback, useMemo } from 'react';
import { Search, ListChecks, Plus } from 'lucide-react';
import { Button, EmptyState } from '@/components/ui';
import { RunRowCard } from '@/features/evalRuns/components';
import { fetchEvalRuns, deleteEvalRun } from '@/services/api/evalRunsApi';
import { jobsApi } from '@/services/api/jobsApi';
import { notificationService } from '@/services/notifications';
import { useUIStore } from '@/stores';
import { routes } from '@/config/routes';
import { timeAgo, formatDuration } from '@/utils/evalFormatters';
import { isActiveStatus } from '@/utils/runStatus';
import { scoreColor } from '@/utils/scoreUtils';
import { usePoll } from '@/hooks';
import type { EvalRun } from '@/types';

export function InsideSalesRunList() {
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const openModal = useUIStore((s) => s.openModal);

  const loadRuns = useCallback(async () => {
    try {
      const data = await fetchEvalRuns({ app_id: 'inside-sales' });
      setRuns(data);
    } catch {
      // silent
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { loadRuns(); }, [loadRuns]);

  // Poll if any run is active
  const hasActive = runs.some((r) => isActiveStatus(r.status));
  usePoll({ fn: async () => { await loadRuns(); return true; }, enabled: hasActive, intervalMs: 5000 });

  const handleDelete = useCallback(async (runId: string) => {
    try {
      await deleteEvalRun(runId);
      notificationService.success('Run deleted');
      loadRuns();
    } catch {
      notificationService.error('Delete failed');
    }
  }, [loadRuns]);

  const handleCancel = useCallback(async (run: EvalRun) => {
    if (!run.jobId) return;
    try {
      await jobsApi.cancel(run.jobId);
      notificationService.success('Run cancelled');
      loadRuns();
    } catch {
      notificationService.error('Cancel failed');
    }
  }, [loadRuns]);

  const filteredRuns = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return runs;
    return runs.filter((r) => {
      const config = r.config as Record<string, unknown> | undefined;
      const name = (config?.run_name as string) || r.evalType || '';
      return name.toLowerCase().includes(q) || r.id.includes(q);
    });
  }, [runs, searchQuery]);

  const getRunName = (run: EvalRun): string => {
    const config = run.config as Record<string, unknown> | undefined;
    const summary = run.summary as Record<string, unknown> | undefined;
    return (
      (config?.run_name as string) ??
      (summary?.evaluator_name as string) ??
      (config?.evaluator_name as string) ??
      'Call Quality Evaluation'
    );
  };

  const getScore = (run: EvalRun): { display: string; color: string } => {
    const summary = run.summary as Record<string, unknown> | undefined;
    const score = summary?.overall_score as number | undefined;
    if (typeof score !== 'number') return { display: '--', color: 'var(--text-muted)' };
    const rounded = Math.round(score);
    const color = scoreColor(rounded);
    return { display: String(rounded), color };
  };

  const getProgress = (run: EvalRun): { current: number; total: number } | undefined => {
    const summary = run.summary as Record<string, unknown> | undefined;
    const evaluated = summary?.evaluated as number | undefined;
    const total = summary?.total as number | undefined;
    if (typeof evaluated === 'number' && typeof total === 'number') return { current: evaluated, total };
    return undefined;
  };

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between shrink-0 pb-4">
        <h1 className="text-lg font-semibold text-[var(--text-primary)]">Runs</h1>
        <Button size="sm" onClick={() => openModal('insideSalesEval')}>
          <Plus className="h-3.5 w-3.5" />
          New Run
        </Button>
      </div>

      {/* Search */}
      <div className="relative max-w-sm mb-3">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--text-muted)]" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search runs..."
          className="w-full pl-8 pr-3 py-1.5 text-xs rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-accent)]"
        />
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--border-default)] border-t-[var(--color-brand-accent)]" />
        </div>
      ) : filteredRuns.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <EmptyState
            icon={ListChecks}
            title={searchQuery ? 'No matching runs' : 'No evaluation runs yet'}
            description={searchQuery ? 'Try a different search.' : 'Start a new evaluation from the wizard.'}
            action={!searchQuery ? { label: 'New Run', onClick: () => openModal('insideSalesEval') } : undefined}
          />
        </div>
      ) : (
        <div className="flex-1 overflow-auto space-y-1.5">
          {filteredRuns.map((run) => {
            const { display: scoreDisplay, color: scoreColor } = getScore(run);
            const active = isActiveStatus(run.status);
            return (
              <RunRowCard
                key={run.id}
                to={routes.insideSales.runDetail(run.id)}
                status={run.status}
                title={getRunName(run)}
                score={scoreDisplay}
                scoreColor={scoreColor}
                id={run.id}
                timeAgo={run.startedAt ? timeAgo(run.startedAt) : '—'}
                isRunning={active}
                onCancel={active ? () => handleCancel(run) : undefined}
                onDelete={() => handleDelete(run.id)}
                modelName={run.llmModel || undefined}
                provider={run.llmProvider || undefined}
                progress={getProgress(run)}
                metadata={[
                  ...(run.durationMs ? [{ text: formatDuration(Math.round(run.durationMs / 1000)) }] : []),
                ]}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
