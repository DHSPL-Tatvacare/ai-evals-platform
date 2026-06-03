import type {
  CanonicalCorrectnessThreadEvaluation,
  CanonicalCorrectnessVerdict,
  CanonicalEfficiencyVerdict,
  CanonicalThreadEvaluation,
  CanonicalThreadRuleOutcome,
  CanonicalThreadRuleSource,
  ChatMessage,
  Evaluation,
  EvaluationDetail,
  EvaluationTarget,
  RuleOutcomeStatus,
  ThreadEvalResult,
  ThreadEvalRow,
} from '@/types/evalRuns';
import { getRuleOutcomeStatus } from './ruleCompliance';

const RULE_STATUS_PRIORITY: Record<CanonicalThreadRuleOutcome['status'], number> = {
  VIOLATED: 0,
  FOLLOWED: 1,
  NOT_APPLICABLE: 2,
  NOT_EVALUATED: 3,
};

// Detail.status (PASS|FAIL|NA, the spine vocabulary) → rule outcome status.
const DETAIL_STATUS_TO_RULE: Record<string, RuleOutcomeStatus> = {
  PASS: 'FOLLOWED',
  FAIL: 'VIOLATED',
  NA: 'NOT_APPLICABLE',
};

function toNumber(value: number | string | null | undefined): number | null {
  if (value == null) return null;
  const n = typeof value === 'string' ? Number(value) : value;
  return Number.isFinite(n) ? n : null;
}

function normalizeEfficiencyVerdict(rawVerdict?: string | null): CanonicalEfficiencyVerdict | null {
  const normalized = rawVerdict?.replace(/[^A-Za-z0-9]+/g, '_').replace(/^_+|_+$/g, '').toUpperCase();
  if (
    normalized === 'EFFICIENT'
    || normalized === 'ACCEPTABLE'
    || normalized === 'INCOMPLETE'
    || normalized === 'FRICTION'
    || normalized === 'BROKEN'
    || normalized === 'NOT_APPLICABLE'
  ) {
    return normalized;
  }
  return null;
}

function normalizeCorrectnessVerdict(rawVerdict?: string | null): CanonicalCorrectnessVerdict | null {
  const normalized = rawVerdict?.replace(/[^A-Za-z0-9]+/g, '_').replace(/^_+|_+$/g, '').toUpperCase();
  if (
    normalized === 'PASS'
    || normalized === 'SOFT_FAIL'
    || normalized === 'HARD_FAIL'
    || normalized === 'CRITICAL'
    || normalized === 'NOT_APPLICABLE'
  ) {
    return normalized;
  }
  return null;
}

function ruleSourceFromDetail(
  detail: EvaluationDetail,
  sourceType: CanonicalThreadRuleSource['sourceType'],
  sourceLabel: string,
): CanonicalThreadRuleSource {
  const status = DETAIL_STATUS_TO_RULE[(detail.status ?? '').toUpperCase()] ?? 'NOT_EVALUATED';
  return {
    sourceType,
    sourceLabel,
    ruleId: detail.key,
    section: detail.label ?? undefined,
    evidence: detail.explanation ?? '',
    status,
    followed: status === 'FOLLOWED' ? true : status === 'VIOLATED' ? false : null,
  };
}

function aggregateRuleOutcomes(ruleSources: CanonicalThreadRuleSource[]): CanonicalThreadRuleOutcome[] {
  const grouped = new Map<string, CanonicalThreadRuleSource[]>();
  for (const source of ruleSources) {
    grouped.set(source.ruleId, [...(grouped.get(source.ruleId) ?? []), source]);
  }

  return Array.from(grouped.entries())
    .map(([ruleId, sources]) => {
      const winning = [...sources].sort((left, right) => RULE_STATUS_PRIORITY[left.status] - RULE_STATUS_PRIORITY[right.status])[0];
      return {
        ruleId,
        section: sources.find((source) => source.section)?.section,
        evidence: winning.evidence,
        status: winning.status,
        followed: winning.status === 'FOLLOWED' ? true : winning.status === 'VIOLATED' ? false : null,
        sources,
      };
    })
    .sort((left, right) => {
      const byStatus = RULE_STATUS_PRIORITY[left.status] - RULE_STATUS_PRIORITY[right.status];
      return byStatus !== 0 ? byStatus : left.ruleId.localeCompare(right.ruleId);
    });
}

function findEvaluation(target: EvaluationTarget, name: string): Evaluation | undefined {
  return target.evaluations.find((e) => e.evaluatorRef?.name === name);
}

function ruleDetails(evaluation: Evaluation | undefined): EvaluationDetail[] {
  return (evaluation?.details ?? []).filter((d) => d.style === 'rule');
}

/**
 * Build the frozen thread view-model from the structured spine target.
 *
 * The spine carries the evaluator verdicts + rule-compliance atoms; the rich
 * provenance the spine does not store (per-message transcript, intent
 * evaluations, friction turns, recovery quality, reasoning, custom outputs,
 * sanity sub-checks) is read from the raw ``result`` it travels with.
 */
function buildCanonicalFromSpine(
  target: EvaluationTarget,
  result: ThreadEvalResult | undefined,
  row?: ThreadEvalRow,
): CanonicalThreadEvaluation {
  const messages = result?.thread?.messages ?? [];

  const correctnessEval = findEvaluation(target, 'correctness');
  const efficiencyEval = findEvaluation(target, 'efficiency');
  const intentEval = findEvaluation(target, 'intent');

  const efficiencyRuleOutcomes = ruleDetails(efficiencyEval)
    .map((detail) => ruleSourceFromDetail(detail, 'efficiency', 'Efficiency'));

  // The spine carries correctness rule atoms on one evaluation (no per-message
  // split). The raw result still holds the per-message correctness rows the
  // table renders; rule outcomes are sourced from the spine to keep the
  // aggregate identical to the persisted atoms.
  const rawCorrectness = result?.correctness_evaluations ?? [];
  const correctnessEvaluations: CanonicalCorrectnessThreadEvaluation[] = rawCorrectness.map((evaluation, index) => ({
    message: evaluation.message,
    verdict: normalizeCorrectnessVerdict(evaluation.verdict),
    reasoning: evaluation.reasoning,
    hasImageContext: evaluation.has_image_context,
    calorieSanity: evaluation.calorie_sanity,
    arithmeticConsistency: evaluation.arithmetic_consistency,
    quantityCoherence: evaluation.quantity_coherence,
    ruleOutcomes: (evaluation.rule_compliance ?? [])
      .map((rule): CanonicalThreadRuleSource => {
        const status = getRuleOutcomeStatus({ status: rule.status, followed: rule.followed ?? null });
        return {
          sourceType: 'correctness',
          sourceLabel: `Correctness #${index + 1}`,
          ruleId: rule.rule_id,
          section: rule.section,
          evidence: rule.evidence ?? '',
          status,
          followed: status === 'FOLLOWED' ? true : status === 'VIOLATED' ? false : null,
        };
      })
      .filter((rule) => Boolean(rule.ruleId)),
  }));

  const correctnessRuleSources = ruleDetails(correctnessEval)
    .map((detail) => ruleSourceFromDetail(detail, 'correctness', 'Correctness'));

  const allRuleOutcomes = [...efficiencyRuleOutcomes, ...correctnessRuleSources];
  const canonicalRuleOutcomes = aggregateRuleOutcomes(allRuleOutcomes);
  const followed = canonicalRuleOutcomes.filter((rule) => rule.status === 'FOLLOWED').length;
  const violated = canonicalRuleOutcomes.filter((rule) => rule.status === 'VIOLATED').length;
  const notApplicable = canonicalRuleOutcomes.filter((rule) => rule.status === 'NOT_APPLICABLE').length;
  const notEvaluated = canonicalRuleOutcomes.filter((rule) => rule.status === 'NOT_EVALUATED').length;

  const efficiencyVerdict = normalizeEfficiencyVerdict(
    efficiencyEval?.verdict ?? result?.efficiency_evaluation?.verdict ?? row?.efficiency_verdict ?? null,
  );
  const worstCorrectness = normalizeCorrectnessVerdict(
    correctnessEval?.verdict ?? result?.worst_correctness_verdict ?? row?.worst_correctness ?? null,
  );
  const intentAccuracy = toNumber(intentEval?.headlineScore)
    ?? result?.intent_accuracy
    ?? row?.intent_accuracy
    ?? null;

  const attributes = (target.attributes ?? {}) as Record<string, unknown>;

  return {
    version: 1,
    facts: {
      thread: {
        threadId: target.targetKey || result?.thread?.thread_id || row?.thread_id || '',
        userId: result?.thread?.user_id ?? (typeof attributes.user_id === 'string' ? attributes.user_id : ''),
        messageCount: result?.thread?.message_count ?? messages.length,
        durationSeconds: result?.thread?.duration_seconds ?? 0,
        hasImage: messages.some((message: ChatMessage) => message.has_image),
      },
      execution: {
        failedEvaluators: result?.failed_evaluators ?? {},
        skippedEvaluators: result?.skipped_evaluators ?? [],
        hadEvaluationError: Boolean(result?.error || result?.failed_evaluators)
          || target.evaluations.some((e) => e.status === 'error'),
      },
    },
    evaluators: {
      intent: {
        accuracy: intentAccuracy,
        evaluations: result?.intent_evaluations ?? [],
      },
      efficiency: {
        verdict: efficiencyVerdict,
        taskCompleted: result?.efficiency_evaluation?.task_completed ?? Boolean(result?.success_status ?? row?.success_status),
        frictionTurns: result?.efficiency_evaluation?.friction_turns ?? [],
        recoveryQuality: result?.efficiency_evaluation?.recovery_quality ?? null,
        failureReason: result?.efficiency_evaluation?.failure_reason ?? result?.efficiency_evaluation?.abandonment_reason ?? '',
        reasoning: efficiencyEval?.reasoning ?? result?.efficiency_evaluation?.reasoning ?? '',
        ruleOutcomes: efficiencyRuleOutcomes,
      },
      correctness: {
        worstVerdict: worstCorrectness,
        evaluations: correctnessEvaluations,
      },
      custom: result?.custom_evaluations ?? {},
    },
    derived: {
      successStatus: Boolean(result?.success_status ?? row?.success_status),
      worstCorrectnessVerdict: worstCorrectness,
      efficiencyVerdict,
      canonicalRuleOutcomes,
      ruleComplianceSummary: {
        followed,
        violated,
        notApplicable,
        notEvaluated,
        evaluatedCount: followed + violated,
      },
    },
  };
}

function buildFallbackCanonicalThreadEvaluation(
  result: ThreadEvalResult,
  row?: ThreadEvalRow,
): CanonicalThreadEvaluation {
  const messages = result.thread?.messages ?? [];
  const efficiencyRuleOutcomes = (result.efficiency_evaluation?.rule_compliance ?? [])
    .map((rule) => toCanonicalRuleSource(rule, 'efficiency', 'Efficiency'))
    .filter((rule): rule is CanonicalThreadRuleSource => Boolean(rule));

  const correctnessEvaluations: CanonicalCorrectnessThreadEvaluation[] = (result.correctness_evaluations ?? []).map((evaluation, index) => ({
    message: evaluation.message,
    verdict: normalizeCorrectnessVerdict(evaluation.verdict),
    reasoning: evaluation.reasoning,
    hasImageContext: evaluation.has_image_context,
    calorieSanity: evaluation.calorie_sanity,
    arithmeticConsistency: evaluation.arithmetic_consistency,
    quantityCoherence: evaluation.quantity_coherence,
    ruleOutcomes: (evaluation.rule_compliance ?? [])
      .map((rule) => toCanonicalRuleSource(rule, 'correctness', `Correctness #${index + 1}`))
      .filter((rule): rule is CanonicalThreadRuleSource => Boolean(rule)),
  }));

  const allRuleOutcomes = [
    ...efficiencyRuleOutcomes,
    ...correctnessEvaluations.flatMap((evaluation) => evaluation.ruleOutcomes),
  ];
  const canonicalRuleOutcomes = aggregateRuleOutcomes(allRuleOutcomes);
  const followed = canonicalRuleOutcomes.filter((rule) => rule.status === 'FOLLOWED').length;
  const violated = canonicalRuleOutcomes.filter((rule) => rule.status === 'VIOLATED').length;
  const notApplicable = canonicalRuleOutcomes.filter((rule) => rule.status === 'NOT_APPLICABLE').length;
  const notEvaluated = canonicalRuleOutcomes.filter((rule) => rule.status === 'NOT_EVALUATED').length;

  return {
    version: 1,
    facts: {
      thread: {
        threadId: result.thread?.thread_id ?? row?.thread_id ?? '',
        userId: result.thread?.user_id ?? '',
        messageCount: result.thread?.message_count ?? messages.length,
        durationSeconds: result.thread?.duration_seconds ?? 0,
        hasImage: messages.some((message: ChatMessage) => message.has_image),
      },
      execution: {
        failedEvaluators: result.failed_evaluators ?? {},
        skippedEvaluators: result.skipped_evaluators ?? [],
        hadEvaluationError: Boolean(result.error || result.failed_evaluators),
      },
    },
    evaluators: {
      intent: {
        accuracy: result.intent_accuracy ?? row?.intent_accuracy ?? null,
        evaluations: result.intent_evaluations ?? [],
      },
      efficiency: {
        verdict: normalizeEfficiencyVerdict(result.efficiency_evaluation?.verdict ?? row?.efficiency_verdict ?? null),
        taskCompleted: result.efficiency_evaluation?.task_completed ?? Boolean(result.success_status ?? row?.success_status),
        frictionTurns: result.efficiency_evaluation?.friction_turns ?? [],
        recoveryQuality: result.efficiency_evaluation?.recovery_quality ?? null,
        failureReason: result.efficiency_evaluation?.failure_reason ?? result.efficiency_evaluation?.abandonment_reason ?? '',
        reasoning: result.efficiency_evaluation?.reasoning ?? '',
        ruleOutcomes: efficiencyRuleOutcomes,
      },
      correctness: {
        worstVerdict: normalizeCorrectnessVerdict(result.worst_correctness_verdict ?? row?.worst_correctness ?? null),
        evaluations: correctnessEvaluations,
      },
      custom: result.custom_evaluations ?? {},
    },
    derived: {
      successStatus: Boolean(result.success_status ?? row?.success_status),
      worstCorrectnessVerdict: normalizeCorrectnessVerdict(result.worst_correctness_verdict ?? row?.worst_correctness ?? null),
      efficiencyVerdict: normalizeEfficiencyVerdict(result.efficiency_evaluation?.verdict ?? row?.efficiency_verdict ?? null),
      canonicalRuleOutcomes,
      ruleComplianceSummary: {
        followed,
        violated,
        notApplicable,
        notEvaluated,
        evaluatedCount: followed + violated,
      },
    },
  };
}

function toCanonicalRuleSource(
  rule: { rule_id?: string; section?: string; evidence?: string; status?: CanonicalThreadRuleOutcome['status']; followed?: boolean | null },
  sourceType: CanonicalThreadRuleSource['sourceType'],
  sourceLabel: string,
): CanonicalThreadRuleSource | null {
  if (!rule.rule_id) {
    return null;
  }
  const status = getRuleOutcomeStatus({
    status: rule.status,
    followed: rule.followed ?? null,
  });
  return {
    sourceType,
    sourceLabel,
    ruleId: rule.rule_id,
    section: rule.section,
    evidence: rule.evidence ?? '',
    status,
    followed: status === 'FOLLOWED' ? true : status === 'VIOLATED' ? false : null,
  };
}

export function getCanonicalThreadEvaluation(
  result: ThreadEvalResult,
  row?: ThreadEvalRow,
): CanonicalThreadEvaluation {
  if (result.canonical_thread) return result.canonical_thread;
  if (row?.canonical_thread) return row.canonical_thread;
  const target = row?.target;
  if (target) return buildCanonicalFromSpine(target, result, row);
  return buildFallbackCanonicalThreadEvaluation(result, row);
}
