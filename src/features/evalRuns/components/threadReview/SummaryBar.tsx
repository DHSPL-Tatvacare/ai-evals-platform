import { useMemo } from 'react';
import type { ThreadEvalRow, ThreadEvalResult, EvaluatorDescriptor } from '@/types/evalRuns';
import VerdictBadge from '../VerdictBadge';
import { OutputFieldRenderer } from '../OutputFieldRenderer';
import { pct } from '@/utils/evalFormatters';
import { InlineReviewControls, useInlineReviewOptional } from '@/features/reviews/inline';

interface Props {
  evalRow: ThreadEvalRow;
  result: ThreadEvalResult;
  evaluatorDescriptors?: EvaluatorDescriptor[];
  threadId?: string;
}

function MetaStatusPill({ status }: { status: 'failed' | 'skipped' }) {
  const isFailed = status === 'failed';
  return (
    <span
      className={`inline-block rounded-full px-1.5 py-px text-[10px] font-semibold tracking-wide leading-snug ${
        isFailed
          ? 'bg-[var(--color-error)] text-white'
          : 'bg-[var(--text-muted)] text-white opacity-60'
      }`}
    >
      {isFailed ? 'Failed' : 'Skipped'}
    </span>
  );
}

export default function SummaryBar({ evalRow, result, evaluatorDescriptors, threadId }: Props) {
  const failed = result.failed_evaluators ?? {};
  const skipped = result.skipped_evaluators ?? [];
  const review = useInlineReviewOptional();

  const reviewableItem = useMemo(() => {
    if (!review?.context || !threadId) return undefined;
    return review.context.items.find((item) => {
      const rawKey = item.itemKey.includes(':') ? item.itemKey.split(':').slice(1).join(':') : item.itemKey;
      return rawKey === threadId;
    });
  }, [review?.context, threadId]);

  // Custom evaluator primary metrics
  const customMetrics: { name: string; descriptor: EvaluatorDescriptor; output: Record<string, unknown> }[] = [];
  if (result.custom_evaluations && evaluatorDescriptors) {
    for (const [, ce] of Object.entries(result.custom_evaluations)) {
      if (ce.status !== 'completed' || !ce.output) continue;
      const desc = evaluatorDescriptors.find(d => d.id === ce.evaluator_id);
      if (desc?.outputSchema?.length) {
        customMetrics.push({ name: ce.evaluator_name, descriptor: desc, output: ce.output });
      }
    }
  }

  const metrics = [
    {
      key: 'efficiency',
      label: 'Efficiency',
      attrKey: 'efficiency_verdict',
      content: failed.efficiency ? (
        <MetaStatusPill status="failed" />
      ) : skipped.includes('efficiency') ? (
        <MetaStatusPill status="skipped" />
      ) : evalRow.efficiency_verdict ? (
        <VerdictBadge verdict={evalRow.efficiency_verdict} category="efficiency" />
      ) : (
        <span className="text-[var(--text-muted)]">{'\u2014'}</span>
      ),
    },
    {
      key: 'correctness',
      label: 'Correctness',
      attrKey: 'worst_correctness',
      content: failed.correctness ? (
        <MetaStatusPill status="failed" />
      ) : skipped.includes('correctness') ? (
        <MetaStatusPill status="skipped" />
      ) : evalRow.worst_correctness ? (
        <VerdictBadge verdict={evalRow.worst_correctness} category="correctness" />
      ) : (
        <span className="text-[var(--text-muted)]">{'\u2014'}</span>
      ),
    },
    {
      key: 'intent',
      label: 'Judge Intent',
      content: failed.intent ? (
        <MetaStatusPill status="failed" />
      ) : skipped.includes('intent') ? (
        <MetaStatusPill status="skipped" />
      ) : evalRow.intent_accuracy != null ? (
        <span className="font-semibold text-[var(--text-primary)]">{pct(evalRow.intent_accuracy)}</span>
      ) : (
        <span className="text-[var(--text-muted)]">{'\u2014'}</span>
      ),
    },
    ...customMetrics.map(cm => ({
      key: cm.descriptor.id,
      label: cm.name,
      content: <OutputFieldRenderer schema={cm.descriptor.outputSchema!} output={cm.output} mode="badge" />,
    })),
    {
      key: 'completed',
      label: 'Status',
      content: evalRow.success_status ? (
        <span className="text-[var(--color-success)] font-semibold">{'\u2713'} Completed</span>
      ) : (
        <span className="text-[var(--color-error)] font-semibold">{'\u2717'} Incomplete</span>
      ),
    },
  ];

  return (
    <div
      className="inline-flex items-stretch rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-sm"
    >
      {metrics.map((m, i) => {
        const attr = m.attrKey && reviewableItem
          ? reviewableItem.attributes.find((a) => a.key === m.attrKey)
          : undefined;
        const edit = attr && reviewableItem
          ? review?.getEdit(reviewableItem.itemKey, attr.key)
          : undefined;
        return (
          <div
            key={m.key}
            className={`flex flex-col items-center justify-center gap-0.5 px-4 py-2 ${
              i > 0 ? 'border-l border-[var(--border-subtle)]' : ''
            }`}
          >
            <span className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] leading-none">{m.label}</span>
            <span className="leading-none flex items-center gap-1">
              {m.content}
              {review?.isEditing && attr && reviewableItem && (
                <InlineReviewControls
                  decision={edit?.decision}
                  note={edit?.note}
                  originalValue={attr.originalValue}
                  reviewedValue={edit?.reviewedValue}
                  allowedValues={attr.allowedValues}
                  onReject={() => review.acceptAttribute(reviewableItem, attr)}
                  onOverride={(v) => review.correctAttribute(reviewableItem, attr, v)}
                  onNote={(n) => review.setAttributeNote(reviewableItem, attr, n)}
                  onClear={() => review.clearAttribute(reviewableItem, attr)}
                />
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}

