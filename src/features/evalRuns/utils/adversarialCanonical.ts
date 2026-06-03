import type {
  AdversarialEvalRow,
  AdversarialResult,
  AdversarialVerdict,
  CanonicalAdversarialCase,
  CanonicalGoalVerdict,
  CanonicalRuleOutcome,
  Difficulty,
  Evaluation,
  EvaluationTarget,
  RuleOutcomeStatus,
} from '@/types/evalRuns';

// Detail.status (PASS|FAIL|NA, the spine vocabulary) → rule outcome status.
const DETAIL_STATUS_TO_RULE: Record<string, RuleOutcomeStatus> = {
  PASS: 'FOLLOWED',
  FAIL: 'VIOLATED',
  NA: 'NOT_APPLICABLE',
};

const ADVERSARIAL_VERDICTS: readonly AdversarialVerdict[] = ['PASS', 'SOFT FAIL', 'HARD FAIL', 'CRITICAL'];

function normalizeAdversarialVerdict(value?: string | null): AdversarialVerdict | null {
  if (!value) return null;
  return (ADVERSARIAL_VERDICTS as readonly string[]).includes(value) ? (value as AdversarialVerdict) : null;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];
}

function withRetryableDerivedFields(caseRecord: CanonicalAdversarialCase): CanonicalAdversarialCase {
  return {
    ...caseRecord,
    derived: {
      ...caseRecord.derived,
      isRetryable: caseRecord.derived.isRetryable ?? caseRecord.derived.isInfraFailure,
    },
  };
}

function fallbackCanonicalCase(result: AdversarialResult, row?: AdversarialEvalRow): CanonicalAdversarialCase {
  const transcript = result.transcript;
  const goalFlow = result.test_case.goal_flow ?? row?.goal_flow ?? [];
  const activeTraits = result.test_case.active_traits ?? row?.active_traits ?? [];
  const goalVerdicts: CanonicalGoalVerdict[] = (result.goal_verdicts ?? []).map((item) => ({
    goalId: item.goal_id,
    achieved: item.achieved,
    reasoning: item.reasoning,
  }));
  return {
    facts: {
      testCase: {
        goalFlow,
        difficulty: result.test_case.difficulty,
        activeTraits,
        syntheticInput: result.test_case.synthetic_input,
        expectedChallenges: result.test_case.expected_challenges ?? [],
      },
      transcript: {
        turns: transcript?.turns ?? [],
        turnCount: transcript?.total_turns ?? row?.total_turns ?? 0,
      },
      transport: {
        hadHttpError: Boolean(result.error),
        hadStreamError: false,
        hadTimeout: Boolean(result.error?.toLowerCase().includes('timeout')),
        hadEmptyFinalAssistantMessage: false,
        hadPartialResponse: false,
        httpErrors: result.error ? [result.error] : [],
        streamErrors: [],
      },
      simulator: {
        goalAchieved: Boolean(transcript?.goal_achieved),
        goalAbandoned: Boolean((transcript?.goals_abandoned?.length ?? 0) > 0),
        goalsAttempted: transcript?.goals_attempted ?? goalFlow,
        goalsCompleted: transcript?.goals_completed ?? [],
        goalsAbandoned: transcript?.goals_abandoned ?? [],
        goalTransitions: transcript?.goal_transitions ?? [],
        stopReason: '',
        failureReason: transcript?.failure_reason ?? transcript?.abandonment_reason ?? '',
      },
    },
    judge: {
      verdict: result.verdict ?? row?.verdict ?? null,
      goalAchieved: Boolean(result.goal_achieved ?? row?.goal_achieved),
      goalVerdicts,
      ruleOutcomes: (result.rule_compliance ?? []).map((item) => ({
        ruleId: item.rule_id,
        status: item.status ?? (item.followed === true ? 'FOLLOWED' : item.followed === false ? 'VIOLATED' : 'NOT_EVALUATED'),
        evidence: item.evidence,
        section: item.section,
      })),
      failureModes: result.failure_modes ?? [],
      reasoning: result.reasoning,
    },
    derived: {
      hasContradiction:
        Boolean(transcript?.goal_achieved) !== Boolean(result.goal_achieved ?? row?.goal_achieved),
      contradictionTypes:
        Boolean(transcript?.goal_achieved) !== Boolean(result.goal_achieved ?? row?.goal_achieved)
          ? ['simulator_goal_vs_judge_goal']
          : [],
      isInfraFailure: Boolean(result.error ?? (row?.verdict == null && row?.error)),
      isRetryable: Boolean(
        row?.is_retryable ??
        result.canonical_case?.derived?.isRetryable ??
        result.error ??
        (row?.is_infra_failure || (row?.verdict == null && row?.error)),
      ),
    },
  };
}

function adversarialEvaluation(target: EvaluationTarget): Evaluation | undefined {
  return target.evaluations.find((e) => e.evaluatorRef?.name === 'adversarial') ?? target.evaluations[0];
}

/**
 * Build the frozen adversarial view-model from the structured spine target.
 *
 * The spine carries the judge verdict, goal-achieved headline, the rule-
 * compliance atoms, and the test-case metadata on ``attributes``. The rich
 * provenance the spine does not store (transcript turns, simulator goal
 * lifecycle, transport errors, per-goal verdicts, failure modes, reasoning) is
 * read from the raw ``result`` it travels with.
 */
function buildCanonicalFromSpine(
  target: EvaluationTarget,
  result: AdversarialResult,
  row?: AdversarialEvalRow,
): CanonicalAdversarialCase {
  const evaluation = adversarialEvaluation(target);
  const attributes = (target.attributes ?? {}) as Record<string, unknown>;
  const transcript = result.transcript;

  const goalFlow = asStringArray(attributes.goal_flow).length
    ? asStringArray(attributes.goal_flow)
    : result.test_case.goal_flow ?? row?.goal_flow ?? [];
  const activeTraits = asStringArray(attributes.active_traits).length
    ? asStringArray(attributes.active_traits)
    : result.test_case.active_traits ?? row?.active_traits ?? [];
  const difficulty = (typeof attributes.difficulty === 'string'
    ? (attributes.difficulty as Difficulty)
    : result.test_case.difficulty);

  const goalVerdicts: CanonicalGoalVerdict[] = (result.goal_verdicts ?? []).map((item) => ({
    goalId: item.goal_id,
    achieved: item.achieved,
    reasoning: item.reasoning,
  }));

  const verdict = normalizeAdversarialVerdict(evaluation?.verdict)
    ?? result.verdict
    ?? row?.verdict
    ?? null;
  const goalAchieved = Boolean(result.goal_achieved ?? row?.goal_achieved);
  const simulatorGoalAchieved = Boolean(transcript?.goal_achieved);

  const ruleOutcomes: CanonicalRuleOutcome[] = (evaluation?.details ?? [])
    .filter((detail) => detail.style === 'rule')
    .map((detail) => ({
      ruleId: detail.key,
      status: DETAIL_STATUS_TO_RULE[(detail.status ?? '').toUpperCase()] ?? 'NOT_EVALUATED',
      evidence: detail.explanation ?? '',
      section: detail.label ?? undefined,
    }));

  const isInfraFailure = Boolean(result.error ?? (row?.verdict == null && row?.error));

  return {
    facts: {
      testCase: {
        goalFlow,
        difficulty,
        activeTraits,
        syntheticInput: result.test_case.synthetic_input,
        expectedChallenges: result.test_case.expected_challenges ?? [],
      },
      transcript: {
        turns: transcript?.turns ?? [],
        turnCount: transcript?.total_turns ?? row?.total_turns ?? 0,
      },
      transport: {
        hadHttpError: Boolean(result.error),
        hadStreamError: false,
        hadTimeout: Boolean(result.error?.toLowerCase().includes('timeout')),
        hadEmptyFinalAssistantMessage: false,
        hadPartialResponse: false,
        httpErrors: result.error ? [result.error] : [],
        streamErrors: [],
      },
      simulator: {
        goalAchieved: simulatorGoalAchieved,
        goalAbandoned: Boolean((transcript?.goals_abandoned?.length ?? 0) > 0),
        goalsAttempted: transcript?.goals_attempted ?? goalFlow,
        goalsCompleted: transcript?.goals_completed ?? [],
        goalsAbandoned: transcript?.goals_abandoned ?? [],
        goalTransitions: transcript?.goal_transitions ?? [],
        stopReason: '',
        failureReason: transcript?.failure_reason ?? transcript?.abandonment_reason ?? '',
      },
    },
    judge: {
      verdict,
      goalAchieved,
      goalVerdicts,
      ruleOutcomes,
      failureModes: result.failure_modes ?? [],
      reasoning: evaluation?.reasoning ?? result.reasoning,
    },
    derived: {
      hasContradiction: simulatorGoalAchieved !== goalAchieved,
      contradictionTypes: simulatorGoalAchieved !== goalAchieved ? ['simulator_goal_vs_judge_goal'] : [],
      isInfraFailure,
      isRetryable: Boolean(
        row?.is_retryable
        ?? result.error
        ?? (row?.is_infra_failure || (row?.verdict == null && row?.error)),
      ),
    },
  };
}

export function getCanonicalAdversarialCase(
  result: AdversarialResult,
  row?: AdversarialEvalRow,
): CanonicalAdversarialCase {
  const canonical = result.canonical_case
    ?? row?.canonical_case
    ?? (row?.target ? buildCanonicalFromSpine(row.target, result, row) : fallbackCanonicalCase(result, row));
  return withRetryableDerivedFields(canonical);
}

export function getCanonicalGoalVerdicts(
  result: AdversarialResult,
  row?: AdversarialEvalRow,
): CanonicalGoalVerdict[] {
  return getCanonicalAdversarialCase(result, row).judge.goalVerdicts;
}

export function isCanonicalInfraFailure(
  result: AdversarialResult,
  row?: AdversarialEvalRow,
): boolean {
  return getCanonicalAdversarialCase(result, row).derived.isInfraFailure;
}
