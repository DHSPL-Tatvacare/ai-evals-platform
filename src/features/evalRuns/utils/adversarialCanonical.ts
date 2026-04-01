import type {
  AdversarialEvalRow,
  AdversarialResult,
  CanonicalAdversarialCase,
  CanonicalGoalVerdict,
} from '@/types/evalRuns';

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

export function getCanonicalAdversarialCase(
  result: AdversarialResult,
  row?: AdversarialEvalRow,
): CanonicalAdversarialCase {
  const canonical = result.canonical_case ?? row?.canonical_case ?? fallbackCanonicalCase(result, row);
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
