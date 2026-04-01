import type {
  CanonicalCorrectnessThreadEvaluation,
  CanonicalCorrectnessVerdict,
  CanonicalEfficiencyVerdict,
  CanonicalThreadEvaluation,
  CanonicalThreadRuleOutcome,
  CanonicalThreadRuleSource,
  ChatMessage,
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

export function getCanonicalThreadEvaluation(
  result: ThreadEvalResult,
  row?: ThreadEvalRow,
): CanonicalThreadEvaluation {
  return result.canonical_thread ?? row?.canonical_thread ?? buildFallbackCanonicalThreadEvaluation(result, row);
}
