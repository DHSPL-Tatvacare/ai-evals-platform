import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Phone } from 'lucide-react';
import { DataTable, type ColumnDef, type SortState } from '@/components/ui/DataTable';
import { FilterPills } from '@/components/ui';
import {
  useInlineReviewOptional,
  InlineReviewControls,
  useInlineReviewNavigationGuard,
  useReviewTableData,
  getEffectiveAttribute,
} from '@/features/reviews/inline';
import { stripReviewItemPrefix } from '@/features/reviews/keys';
import { StatPill } from '@/features/evalRuns/components';
import VerdictBadge from '@/features/evalRuns/components/VerdictBadge';
import DistributionBar from '@/features/evalRuns/components/DistributionBar';
import { CallResultPanel } from '@/features/crmWorkspace/components/CallResultPanel';
import { formatDuration } from '@/utils/formatters';
import { scoreColor, getScoreBand } from '@/utils/scoreUtils';
import type { AnyRunStatus } from '@/utils/runLifecycle';
import type { ThreadEvalRow } from '@/types';
import {
  RunMetricCards,
  RunResultsEmptyState,
  RunResultsSearch,
} from '../components';
import { getOverallScore } from './callQualityScore';

const BAND_ORDER = ['Strong', 'Good', 'Needs work', 'Poor'] as const;

export interface CallQualityResultsProps {
  runId: string;
  runStatus: AnyRunStatus;
  threads: ThreadEvalRow[];
  searchQuery: string;
  onSearchChange: (q: string) => void;
  /** Entry-provided URL for a call drill-down row. Lets the renderer stay
   *  app-agnostic — the call_quality eval type is the renderer's concern,
   *  the URL prefix (`/inside-sales/...`) is the mounting app's. */
  getCallHref: (threadId: string) => string;
}

export function CallQualityResults({
  runId,
  runStatus,
  threads,
  searchQuery,
  onSearchChange,
  getCallHref,
}: CallQualityResultsProps) {
  const navigate = useNavigate();
  const { confirmNavigation, guardModal } = useInlineReviewNavigationGuard();
  const [sortState, setSortState] = useState<SortState>({ key: 'score', order: 'desc' });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [bandFilter, setBandFilter] = useState<Set<string>>(new Set());

  const bandOptions = useMemo(() => {
    const present = new Set(threads.map((t) => getScoreBand(getOverallScore(t))));
    return BAND_ORDER.filter((b) => present.has(b)).map((b) => ({ id: b, label: b }));
  }, [threads]);

  const toggleBand = (b: string) => {
    setBandFilter((prev) => {
      const next = new Set(prev);
      if (next.has(b)) next.delete(b);
      else next.add(b);
      return next;
    });
    setPage(1);
  };

  const filteredThreads = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    return threads.filter((t) => {
      if (q) {
        const meta = readCallMeta(t);
        const rep = ((meta?.rep_label as string) || '').toLowerCase();
        const lead = ((meta?.lead_id as string) || '').toLowerCase();
        if (!rep.includes(q) && !lead.includes(q) && !t.thread_id.includes(q)) return false;
      }
      if (bandFilter.size > 0 && !bandFilter.has(getScoreBand(getOverallScore(t)))) return false;
      return true;
    });
  }, [threads, searchQuery, bandFilter]);

  const sortedThreads = useMemo(() => {
    const arr = [...filteredThreads];
    arr.sort((a, b) => {
      const cmp = compareCallRows(a, b, sortState.key);
      return sortState.order === 'asc' ? cmp : -cmp;
    });
    return arr;
  }, [filteredThreads, sortState]);

  const totalItems = sortedThreads.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const safePage = Math.min(page, totalPages);
  const pagedThreads = sortedThreads.slice((safePage - 1) * pageSize, safePage * pageSize);

  const evaluated = threads.filter((t) => t.success_status).length;
  const failed = threads.length - evaluated;
  const scores = threads.map(getOverallScore).filter((s): s is number => s !== null);
  const avgScore = scores.length > 0 ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null;
  const scoreBands: Record<string, number> = { Strong: 0, Good: 0, 'Needs work': 0, Poor: 0 };
  scores.forEach((s) => { scoreBands[getScoreBand(s)]++; });

  const { reviewableItems, reviewedIds, humanVerdicts } = useReviewTableData(runId, { itemType: 'call' });
  const hasAnyReviewData = !!reviewableItems || !!humanVerdicts;

  const inScopeCallIds = useMemo(() => {
    const set = new Set<string>();
    if (!reviewableItems) return set;
    for (const itemId of reviewableItems.keys()) {
      set.add(itemId);
    }
    return set;
  }, [reviewableItems]);

  const reviewedCount = reviewedIds?.size ?? 0;

  const reviewedScoreBands = useMemo(() => {
    if (!humanVerdicts || humanVerdicts.size === 0) return null;
    const dist: Record<string, number> = { Strong: 0, Good: 0, 'Needs work': 0, Poor: 0 };
    for (const t of threads) {
      const aiBand = getScoreBand(getOverallScore(t));
      const band = getEffectiveAttribute(humanVerdicts, t.thread_id, 'overall_verdict', aiBand) ?? aiBand;
      if (band in dist) dist[band] += 1;
    }
    return dist;
  }, [humanVerdicts, threads]);

  const columns: ColumnDef<ThreadEvalRow>[] = [
    {
      key: 'agent',
      header: 'Agent',
      sortable: true,
      width: 'min-w-[150px]',
      render: (t) => (
        <span className="text-[var(--text-primary)]">
          {(readCallMeta(t)?.rep_label as string) || '—'}
        </span>
      ),
    },
    {
      key: 'lead',
      header: 'Lead',
      sortable: true,
      width: 'min-w-[150px]',
      render: (t) => (
        <span className="text-[var(--text-primary)]">
          {(readCallMeta(t)?.lead_id as string) || '—'}
        </span>
      ),
    },
    {
      key: 'duration',
      header: 'Duration',
      sortable: true,
      width: 'w-[110px]',
      render: (t) => {
        const duration = (readCallMeta(t)?.duration_seconds as number) || 0;
        return (
          <span className="text-[var(--text-secondary)]">
            {duration > 0 ? formatDuration(duration) : '—'}
          </span>
        );
      },
    },
    {
      key: 'score',
      header: 'Score',
      sortable: true,
      width: 'w-[90px]',
      render: (t) => {
        const score = getOverallScore(t);
        return (
          <span className="font-bold" style={{ color: scoreColor(score) }}>
            {score !== null ? score : '—'}
          </span>
        );
      },
    },
    {
      key: 'band',
      header: 'Band',
      width: 'min-w-[120px]',
      render: (t) => (
        <VerdictBadge
          verdict={getScoreBand(getOverallScore(t))}
          category="status"
          humanVerdict={humanVerdicts?.get(t.thread_id)?.get('overall_verdict')}
        />
      ),
    },
    {
      key: 'status',
      header: 'Status',
      sortable: true,
      width: 'w-[80px]',
      headerClassName: 'text-center',
      cellClassName: 'text-center',
      render: (t) =>
        t.success_status ? (
          <span className="text-[var(--color-success)]">{'✓'}</span>
        ) : (
          <span className="text-[var(--color-error)]">{'✗'}</span>
        ),
    },
    ...(hasAnyReviewData
      ? ([
          {
            key: 'human_review',
            header: 'Human Review',
            width: 'w-[120px]',
            render: (t: ThreadEvalRow) => {
              const isReviewed =
                (reviewedIds?.has(t.thread_id) ?? false) ||
                !!humanVerdicts?.get(t.thread_id);
              return isReviewed ? (
                <span className="font-semibold text-[var(--text-brand)]">Yes</span>
              ) : (
                <span className="text-[var(--text-muted)]">No</span>
              );
            },
          },
        ] satisfies ColumnDef<ThreadEvalRow>[])
      : []),
  ];

  const handleRowClick = (t: ThreadEvalRow) => {
    const target = getCallHref(t.thread_id);
    if (inScopeCallIds.has(t.thread_id)) {
      navigate(target);
      return;
    }
    confirmNavigation(() => navigate(target));
  };

  if (threads.length === 0) {
    return (
      <div className="flex flex-1 min-h-0 flex-col py-2">
        <RunResultsEmptyState
          status={runStatus}
          hasAnyData={false}
          hasFilteredData={false}
          emptyIcon={Phone}
          emptyTitle="No results"
          emptyMessage="No evaluated calls found."
          processingMessage="Results will appear here as calls are evaluated."
        />
      </div>
    );
  }

  return (
    <div className="flex flex-1 min-h-0 flex-col gap-4 py-2">
      <RunMetricCards>
        <StatPill
          label="Calls Evaluated"
          metricKey="calls_evaluated"
          value={`${evaluated} / ${threads.length}`}
        />
        <StatPill
          label="Avg Score"
          metricKey="avg_score"
          value={avgScore !== null ? `${avgScore} / 100` : '—'}
          color={scoreColor(avgScore)}
        />
        <StatPill
          label="Failed"
          metricKey="failed_calls"
          value={String(failed)}
          color={failed > 0 ? 'var(--color-error)' : 'var(--text-muted)'}
        />
        {reviewableItems && reviewableItems.size > 0 && (
          <StatPill
            label="Reviewed"
            metricKey="reviewed_items"
            value={`${reviewedCount} / ${threads.length}`}
            color={reviewedCount > 0 ? 'var(--text-brand)' : undefined}
          />
        )}
      </RunMetricCards>

      {scores.length > 0 && (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="flex items-baseline gap-2 mb-1.5">
              <h4 className="text-[10px] font-medium text-[var(--text-muted)] uppercase">Score Bands</h4>
              {reviewedScoreBands && (
                <span className="text-[10px] uppercase tracking-wider text-[var(--text-brand)] font-semibold">Reviewed</span>
              )}
            </div>
            {reviewedScoreBands ? (
              <div className="space-y-2">
                <div className="opacity-60">
                  <p className="text-[10px] text-[var(--text-muted)] mb-0.5">AI</p>
                  <DistributionBar
                    distribution={scoreBands}
                    order={BAND_ORDER}
                  />
                </div>
                <div>
                  <p className="text-[10px] text-[var(--text-brand)] mb-0.5">Reviewed</p>
                  <DistributionBar
                    distribution={reviewedScoreBands}
                    order={BAND_ORDER}
                  />
                </div>
              </div>
            ) : (
              <DistributionBar
                distribution={scoreBands}
                order={BAND_ORDER}
              />
            )}
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        <RunResultsSearch
          status={runStatus}
          resultCount={threads.length}
          value={searchQuery}
          onChange={onSearchChange}
          placeholder="Search agent, lead…"
          className="w-60 max-w-none"
        />
        {bandOptions.length > 0 && (
          <FilterPills
            size="sm"
            options={bandOptions}
            selected={[...bandFilter]}
            onToggle={toggleBand}
          />
        )}
        <span className="text-xs text-[var(--text-muted)] ml-auto">
          {filteredThreads.length}
          {filteredThreads.length !== threads.length ? ` of ${threads.length}` : ''} calls
        </span>
      </div>

      {filteredThreads.length === 0 ? (
        <RunResultsEmptyState
          status={runStatus}
          hasAnyData={threads.length > 0}
          hasFilteredData={false}
          emptyIcon={Phone}
          emptyTitle="No results"
          emptyMessage="No evaluated calls found."
          processingMessage="Results will appear here as calls are evaluated."
        />
      ) : (
        <DataTable
          columns={columns}
          data={pagedThreads}
          keyExtractor={(t) => String(t.id)}
          onRowClick={handleRowClick}
          sortState={sortState}
          onSortChange={(next) => {
            setSortState(next);
            setPage(1);
          }}
          pagination={{
            page: safePage,
            totalPages,
            pageSize,
            totalItems,
            showCount: true,
            onPageChange: setPage,
            onPageSizeChange: (n) => {
              setPageSize(n);
              setPage(1);
            },
          }}
          minWidth="720px"
          emptyIcon={Phone}
          emptyTitle="No results"
        />
      )}
      {guardModal}
    </div>
  );
}

/** Subject metadata for a call-quality row: prefer the spine target's normalized
 *  attributes (agent / lead_id / duration_seconds), falling back to the raw
 *  `call_metadata` blob for rows without a spine target (e.g. all-errored runs). */
function readCallMeta(t: ThreadEvalRow): Record<string, unknown> | undefined {
  const attrs = (t as unknown as { target?: { attributes?: Record<string, unknown> } }).target
    ?.attributes;
  if (attrs && (attrs.agent != null || attrs.lead_id != null || attrs.duration_seconds != null)) {
    return attrs;
  }
  return (t.result as unknown as Record<string, unknown>)?.call_metadata as
    | Record<string, unknown>
    | undefined;
}

/** Column-keyed comparator for the calls table. Returns ascending order; the
 *  caller flips the sign for descending. Missing values sort last. */
function compareCallRows(a: ThreadEvalRow, b: ThreadEvalRow, key: string): number {
  switch (key) {
    case 'agent':
      return ((readCallMeta(a)?.rep_label as string) || '').localeCompare(
        (readCallMeta(b)?.rep_label as string) || '',
      );
    case 'lead':
      return ((readCallMeta(a)?.lead_id as string) || '').localeCompare(
        (readCallMeta(b)?.lead_id as string) || '',
      );
    case 'duration':
      return (
        ((readCallMeta(a)?.duration_seconds as number) || 0) -
        ((readCallMeta(b)?.duration_seconds as number) || 0)
      );
    case 'score':
      return (getOverallScore(a) ?? -1) - (getOverallScore(b) ?? -1);
    case 'status':
      return a.success_status - b.success_status;
    default:
      return 0;
  }
}

/**
 * Drilldown body for a single call's evaluation result. Mounted by the entry
 * when the URL carries `/calls/:callId`; header chrome stays in the entry
 * until Phase 3 moves it onto a renderer descriptor.
 */
export function CallQualityDrilldown({ thread }: { thread: ThreadEvalRow }) {
  const review = useInlineReviewOptional();
  const { guardModal } = useInlineReviewNavigationGuard();

  const reviewContextItems = review?.context?.items;
  const reviewableItem = useMemo(
    () =>
      reviewContextItems?.find(
        (item) => item.itemType === 'call' && stripReviewItemPrefix(item.itemKey) === thread.thread_id,
      ) ?? null,
    [reviewContextItems, thread.thread_id],
  );

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {reviewableItem && reviewableItem.attributes.length > 0 && (
        <div className="shrink-0 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)]">
          <div className="border-b border-[var(--border-subtle)] px-4 py-3">
            <h3 className="text-sm font-semibold text-[var(--text-primary)]">Review checks</h3>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">
              Review the backend-defined call quality checks for this call.
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-[var(--bg-secondary)]">
                <tr className="border-b border-[var(--border-subtle)]">
                  <th className="px-4 py-2 text-left font-medium text-[var(--text-secondary)]">Check</th>
                  <th className="px-4 py-2 text-left font-medium text-[var(--text-secondary)]">AI Value</th>
                  <th className="px-4 py-2 text-left font-medium text-[var(--text-secondary)]">Review</th>
                  <th className="px-4 py-2 text-left font-medium text-[var(--text-secondary)]">Source</th>
                  {review?.isEditing && (
                    <th className="px-4 py-2 text-left font-medium text-[var(--text-secondary)]">Actions</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {reviewableItem.attributes.map((attr) => {
                  const edit = review?.getEdit(reviewableItem.itemKey, attr.key);
                  const reviewValue =
                    edit?.decision === 'correct'
                      ? edit.reviewedValue ?? '—'
                      : edit?.decision === 'accept'
                      ? 'Accepted'
                      : 'Not reviewed';
                  return (
                    <tr key={attr.key} className="border-b border-[var(--border-subtle)] last:border-b-0">
                      <td className="px-4 py-3">
                        <div className="space-y-0.5">
                          <p className="font-medium text-[var(--text-primary)]">{attr.label}</p>
                          {attr.description && (
                            <p className="text-[11px] text-[var(--text-muted)]">{attr.description}</p>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 font-semibold text-[var(--text-primary)]">
                        {attr.originalValue ?? '—'}
                      </td>
                      <td className="px-4 py-3">
                        <div className="space-y-0.5">
                          <p className="font-medium text-[var(--text-primary)]">{reviewValue}</p>
                          {edit?.note && (
                            <p className="max-w-[240px] truncate text-[11px] text-[var(--text-muted)]">{edit.note}</p>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-[var(--text-secondary)]">
                        {attr.sourceLabel ?? attr.group ?? '—'}
                      </td>
                      {review?.isEditing && (
                        <td className="px-4 py-3">
                          <InlineReviewControls
                            decision={edit?.decision}
                            note={edit?.note}
                            originalValue={attr.originalValue}
                            reviewedValue={edit?.reviewedValue}
                            allowedValues={attr.allowedValues}
                            onReject={() => review.acceptAttribute(reviewableItem, attr)}
                            onOverride={(nextValue) => review.correctAttribute(reviewableItem, attr, nextValue)}
                            onNote={(nextNote) => review.setAttributeNote(reviewableItem, attr, nextNote)}
                            onClear={() => review.clearAttribute(reviewableItem, attr)}
                          />
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <CallResultPanel thread={thread} />
      {guardModal}
    </div>
  );
}

/**
 * Prev/next navigator for siblings in a call-quality drilldown. Mounted by the
 * single-eval run-detail hook into the header `actions` slot when the URL
 * carries `/calls/:callId`. App-agnostic — the caller composes the URL via
 * `getCallHref` so this stays under `resultRenderers/`.
 */
export interface CallQualityCallNavProps {
  thread: ThreadEvalRow;
  siblings: ThreadEvalRow[];
  getCallHref: (threadId: string) => string;
}

export function CallQualityCallNav({ thread, siblings, getCallHref }: CallQualityCallNavProps) {
  const navigate = useNavigate();
  const review = useInlineReviewOptional();
  const { confirmNavigation } = useInlineReviewNavigationGuard();

  const reviewContextItems = review?.context?.items;
  const inScopeCallIds = useMemo(() => {
    const set = new Set<string>();
    if (!reviewContextItems) return set;
    for (const item of reviewContextItems) {
      if (item.itemType !== 'call') continue;
      set.add(stripReviewItemPrefix(item.itemKey));
    }
    return set;
  }, [reviewContextItems]);

  if (siblings.length <= 1) return null;

  const currentIdx = siblings.findIndex((s) => s.thread_id === thread.thread_id);
  const prevThread = currentIdx > 0 ? siblings[currentIdx - 1] : null;
  const nextThread = currentIdx < siblings.length - 1 ? siblings[currentIdx + 1] : null;
  const goToThread = (id: string) => {
    const target = getCallHref(id);
    if (inScopeCallIds.has(id)) {
      navigate(target);
      return;
    }
    confirmNavigation(() => navigate(target));
  };

  return (
    <span className="inline-flex items-center gap-0.5 border border-[var(--border-subtle)] rounded-md bg-[var(--bg-secondary)]">
      <button
        disabled={!prevThread}
        onClick={() => prevThread && goToThread(prevThread.thread_id)}
        className="p-1 disabled:opacity-30 hover:bg-[var(--interactive-secondary)] rounded-l-md transition-colors cursor-pointer disabled:cursor-default"
        title="Previous call"
      >
        <ArrowLeft size={14} />
      </button>
      <span className="text-[10px] tabular-nums px-1 border-x border-[var(--border-subtle)] text-[var(--text-secondary)]">
        {currentIdx + 1}/{siblings.length}
      </span>
      <button
        disabled={!nextThread}
        onClick={() => nextThread && goToThread(nextThread.thread_id)}
        className="p-1 disabled:opacity-30 hover:bg-[var(--interactive-secondary)] rounded-r-md transition-colors cursor-pointer disabled:cursor-default"
        title="Next call"
      >
        <ArrowLeft size={14} className="rotate-180" />
      </button>
    </span>
  );
}

