import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { LoadingState, PageSurface, Select } from '@/components/ui';
import { Tabs } from '@/components/ui/Tabs';
import type {
  ThreadEvalRow,
  ThreadEvalResult,
  CorrectnessVerdict,
  EvaluatorDescriptor,
} from '@/types';
import { fetchThreadHistory, fetchRun, fetchRunThreads } from '@/services/api/evalRunsApi';
import { formatTimestamp, unwrapSerializedDates } from '@/utils/evalFormatters';
import { runDetailForApp, runsForApp, threadDetailForApp } from '@/config/routes';
import { useCurrentAppId } from '@/hooks';
import { usePageMetadata } from '@/config/pageMetadata';
import { useAppPageActions } from '@/features/pageActions/registry';
import {
  useEvalLinking,
  SummaryBar,
  LinkedChatViewer,
  EfficiencyTab,
  CorrectnessTab,
  IntentTab,
  CustomEvalsTab,
  RuleComplianceTab,
} from '../components/threadReview';
import type { EvalTab } from '../components/threadReview';
import { getCanonicalThreadEvaluation } from '../utils/threadCanonical';
import {
  InlineReviewProvider,
} from '@/features/reviews/inline';
import { usePermission } from '@/utils/permissions';

export default function ThreadDetailV2() {
  const { threadId } = useParams<{ threadId: string }>();
  const navigate = useNavigate();
  const appId = useCurrentAppId();
  const { icon } = usePageMetadata('threadDetail');
  const extraActions = useAppPageActions('threadDetail');
  const [searchParams] = useSearchParams();
  const runIdParam = searchParams.get('runId');
  const [history, setHistory] = useState<ThreadEvalRow[]>([]);
  const [selected, setSelected] = useState<number>(0);
  const [error, setError] = useState('');
  const [evaluatorDescriptors, setEvaluatorDescriptors] = useState<EvaluatorDescriptor[]>();
  const [siblingThreadIds, setSiblingThreadIds] = useState<string[]>([]);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!threadId) return;
    fetchThreadHistory(threadId)
      .then((r) => {
        setHistory(r.history);
        // Preselect the entry that matches ?runId= so navigation from a
        // specific run lands on that run's evaluation (required for review
        // mode to apply and for rule-level overrides to render).
        if (runIdParam) {
          const idx = r.history.findIndex((h) => h.run_id === runIdParam);
          if (idx >= 0) setSelected(idx);
        }
      })
      .catch((e: Error) => setError(e.message));
  }, [threadId, runIdParam]);

  const current = history[selected];
  const result = useMemo(
    () => current?.result ? unwrapSerializedDates(current.result) as ThreadEvalResult : undefined,
    [current?.result],
  );
  const canonicalThread = useMemo(
    () => (result ? getCanonicalThreadEvaluation(result, current) : null),
    [current, result],
  );

  useEffect(() => {
    if (!current?.run_id) return;
    fetchRun(current.run_id)
      .then((run) => {
        if (run.evaluator_descriptors) {
          setEvaluatorDescriptors(run.evaluator_descriptors);
        }
      })
      .catch(() => { /* descriptors are optional */ });

    // Fetch sibling threads for prev/next navigation
    fetchRunThreads(current.run_id)
      .then((r) => setSiblingThreadIds(r.evaluations.map((e) => e.thread_id)))
      .catch(() => { /* navigation is optional */ });
  }, [current?.run_id]);

  const siblingIndex = siblingThreadIds.indexOf(threadId ?? '');
  const prevThreadId = siblingIndex > 0 ? siblingThreadIds[siblingIndex - 1] : null;
  const nextThreadId = siblingIndex >= 0 && siblingIndex < siblingThreadIds.length - 1 ? siblingThreadIds[siblingIndex + 1] : null;

  const goToThread = useCallback(
    (id: string) => {
      const detailPath = threadDetailForApp(appId, id, current?.run_id);
      if (detailPath) {
        navigate(detailPath);
      }
    },
    [appId, navigate, current?.run_id],
  );

  // Keyboard shortcuts: left/right arrow with Alt key
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!e.altKey) return;
      if (e.key === 'ArrowLeft' && prevThreadId) { e.preventDefault(); goToThread(prevThreadId); }
      if (e.key === 'ArrowRight' && nextThreadId) { e.preventDefault(); goToThread(nextThreadId); }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [prevThreadId, nextThreadId, goToThread]);

  const messages = useMemo(
    () => result?.thread?.messages ?? [],
    [result?.thread?.messages],
  );

  const correctnessMap = useMemo(() => {
    const map = new Map<number, CorrectnessVerdict>();
    if (!result?.correctness_evaluations) return map;
    for (const ce of result.correctness_evaluations) {
      const idx = messages.findIndex(m => m.query_text === ce.message?.query_text);
      if (idx >= 0) map.set(idx, ce.verdict);
    }
    return map;
  }, [result?.correctness_evaluations, messages]);

  const intentMap = useMemo(() => {
    const map = new Map<number, boolean>();
    if (!result?.intent_evaluations) return map;
    for (const ie of result.intent_evaluations) {
      const idx = messages.findIndex(m => m.query_text === ie.message?.query_text);
      if (idx >= 0) map.set(idx, ie.is_correct_intent);
    }
    return map;
  }, [result?.intent_evaluations, messages]);

  const frictionTurns = useMemo(() => {
    const set = new Set<number>();
    if (!result?.efficiency_evaluation?.friction_turns) return set;
    for (const ft of result.efficiency_evaluation.friction_turns) {
      if (ft.turn != null) set.add(ft.turn - 1);
    }
    return set;
  }, [result?.efficiency_evaluation?.friction_turns]);

  const hasCustomEvals = result?.custom_evaluations && Object.keys(result.custom_evaluations).length > 0;
  const hasRules = (canonicalThread?.derived.canonicalRuleOutcomes.length ?? 0) > 0
    || (result?.efficiency_evaluation?.rule_compliance?.length ?? 0) > 0
    || (result?.correctness_evaluations ?? []).some(ce => (ce.rule_compliance?.length ?? 0) > 0);

  const linking = useEvalLinking('efficiency');
  const canReview = usePermission('review:manage');

  const handleTableRowClick = (tab: EvalTab) => (turnIndex: number) => {
    linking.onTableHover(turnIndex);
    if (linking.activeTab !== tab) {
      // stay in current tab
    }
  };

  const tabs = useMemo(() => {
    const failed = result?.failed_evaluators ?? {};
    const skipped = result?.skipped_evaluators ?? [];

    const tabList = [
      {
        id: 'efficiency' as EvalTab,
        label: 'Efficiency',
        content: (
          <EfficiencyTab
            evaluation={result?.efficiency_evaluation ?? null}
            failed={failed.efficiency}
            skipped={skipped.includes('efficiency')}
          />
        ),
      },
      {
        id: 'correctness' as EvalTab,
        label: `Correctness (${result?.correctness_evaluations?.length ?? 0})`,
        content: (
          <CorrectnessTab
            evaluations={result?.correctness_evaluations ?? []}
            activeTurnIndex={linking.activeTab === 'correctness' ? linking.activeTurnIndex : null}
            onRowClick={handleTableRowClick('correctness')}
            failed={failed.correctness}
            skipped={skipped.includes('correctness')}
          />
        ),
      },
      {
        id: 'intent' as EvalTab,
        label: `Judge Intent (${result?.intent_evaluations?.length ?? 0})`,
        content: (
          <IntentTab
            evaluations={result?.intent_evaluations ?? []}
            activeTurnIndex={linking.activeTab === 'intent' ? linking.activeTurnIndex : null}
            onRowClick={handleTableRowClick('intent')}
            failed={failed.intent}
            skipped={skipped.includes('intent')}
          />
        ),
      },
    ];

    if (hasCustomEvals) {
      tabList.push({
        id: 'custom' as EvalTab,
        label: 'Custom',
        content: (
          <CustomEvalsTab
            customEvaluations={result!.custom_evaluations!}
            evaluatorDescriptors={evaluatorDescriptors}
          />
        ),
      });
    }

    if (hasRules) {
      tabList.push({
        id: 'rules' as EvalTab,
        label: 'Rules',
        content: (
          <RuleComplianceTab
            efficiencyEvaluation={result?.efficiency_evaluation}
            correctnessEvaluations={result?.correctness_evaluations}
            canonicalThread={canonicalThread}
            threadId={threadId}
            runId={current?.run_id}
          />
        ),
      });
    }

    return tabList;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result, canonicalThread, linking.activeTab, linking.activeTurnIndex, evaluatorDescriptors, hasCustomEvals, hasRules]);

  if (error) {
    return (
      <div className="bg-[var(--surface-error)] border border-[var(--border-error)] rounded p-3 text-sm text-[var(--color-error)]">
        {error}
      </div>
    );
  }

  if (history.length === 0) {
    return <LoadingState message="Loading thread…" />;
  }

  // ── Shared pieces for surface + legacy returns ──────────
  const threadNavControls = (
    <div className="flex items-center gap-2 shrink-0">
      {history.length > 1 && (
        <Select
          value={String(selected)}
          onChange={(val) => setSelected(Number(val))}
          options={history.map((h, i) => ({
            value: String(i),
            label: [
              formatTimestamp(h.created_at),
              h.worst_correctness ? `• ${h.worst_correctness}` : '',
              h.efficiency_verdict ? `• ${h.efficiency_verdict}` : '',
            ].filter(Boolean).join(' '),
          }))}
          size="sm"
        />
      )}
      {siblingThreadIds.length > 1 && (
        <span className="inline-flex items-center gap-0.5 border border-[var(--border-subtle)] rounded-md bg-[var(--bg-secondary)]">
          <button
            disabled={!prevThreadId}
            onClick={() => prevThreadId && goToThread(prevThreadId)}
            className="p-1 disabled:opacity-30 hover:bg-[var(--surface-hover)] rounded-l-md transition-colors cursor-pointer disabled:cursor-default"
            title={prevThreadId ? `Previous thread (Alt+←)` : 'No previous thread'}
          >
            <ChevronLeft size={14} />
          </button>
          <span className="text-[10px] tabular-nums px-1 border-x border-[var(--border-subtle)]">
            {siblingIndex + 1}/{siblingThreadIds.length}
          </span>
          <button
            disabled={!nextThreadId}
            onClick={() => nextThreadId && goToThread(nextThreadId)}
            className="p-1 disabled:opacity-30 hover:bg-[var(--surface-hover)] rounded-r-md transition-colors cursor-pointer disabled:cursor-default"
            title={nextThreadId ? `Next thread (Alt+→)` : 'No next thread'}
          >
            <ChevronRight size={14} />
          </button>
        </span>
      )}
    </div>
  );

  const summaryBarBlock = current && result ? (
    <div className="shrink-0 overflow-x-auto scrollbar-thin pb-4 border-b border-dashed border-[var(--border-subtle)] mb-3">
      <div className="w-fit mx-auto">
        <SummaryBar evalRow={current} result={result} evaluatorDescriptors={evaluatorDescriptors} threadId={threadId} />
      </div>
    </div>
  ) : null;

  const splitPane = current && result ? (
    <>
      {/* Mobile: stacked */}
      <div className="flex flex-col flex-1 min-h-0 md:hidden">
        <details className="shrink-0" open>
          <summary className="text-xs text-[var(--text-muted)] font-medium cursor-pointer py-1.5 px-1">
            Conversation ({messages.length} messages)
          </summary>
          <div className="max-h-[400px] overflow-y-auto">
            <LinkedChatViewer
              messages={messages}
              correctnessMap={correctnessMap}
              intentMap={intentMap}
              frictionTurns={frictionTurns}
              activeTurnIndex={linking.activeTurnIndex}
              onTurnClick={linking.onChatClick}
              chatContainerRef={chatContainerRef}
            />
          </div>
        </details>
        <div className="flex-1 min-h-0">
          <Tabs
            tabs={tabs}
            defaultTab={linking.activeTab}
            onChange={(tabId) => linking.onTabChange(tabId as EvalTab)}
            fillHeight
          />
        </div>
      </div>

      {/* Desktop: side-by-side */}
      <div className="hidden md:flex flex-1 min-h-0">
        <div className="w-[35%] min-w-[280px] max-w-[420px] flex flex-col min-h-0 border-r border-[var(--border-subtle)]">
          <div className="flex-1 min-h-0 overflow-y-auto">
            <LinkedChatViewer
              messages={messages}
              correctnessMap={correctnessMap}
              intentMap={intentMap}
              frictionTurns={frictionTurns}
              activeTurnIndex={linking.activeTurnIndex}
              onTurnClick={linking.onChatClick}
              chatContainerRef={chatContainerRef}
            />
          </div>
        </div>
        <div className="flex-1 min-w-0 flex flex-col min-h-0">
          <Tabs
            tabs={tabs}
            defaultTab={linking.activeTab}
            onChange={(tabId) => linking.onTabChange(tabId as EvalTab)}
            fillHeight
          />
        </div>
      </div>
    </>
  ) : null;

  const backTarget = current
    ? { to: runDetailForApp(appId, current.run_id), label: current.run_id.slice(0, 12) }
    : { to: runsForApp(appId), label: 'Runs' };

  const title = (threadId ?? '').slice(0, 13) || 'Thread';

  return (
    <InlineReviewProvider runId={current?.run_id ?? ''} appId={appId} enabled={canReview && !!current?.run_id}>
      <PageSurface
        icon={icon}
        title={title}
        back={backTarget}
        actions={
          <>
            {extraActions}
            {threadNavControls}
          </>
        }
      >
        {summaryBarBlock}
        {splitPane}
      </PageSurface>
    </InlineReviewProvider>
  );
}
