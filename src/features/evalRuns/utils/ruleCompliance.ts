import type { RuleOutcomeStatus } from '@/types/evalRuns';

type RuleOutcomeLike = {
  status?: RuleOutcomeStatus;
  followed?: boolean | null;
};

type RuleIdentityLike = RuleOutcomeLike & {
  rule_id?: string;
  ruleId?: string;
};

export interface RuleOutcomeCounts {
  followed: number;
  violated: number;
  notApplicable: number;
  notEvaluated: number;
  evaluatedCount: number;
}

const STATUS_ORDER: Record<RuleOutcomeStatus, number> = {
  VIOLATED: 0,
  FOLLOWED: 1,
  NOT_APPLICABLE: 2,
  NOT_EVALUATED: 3,
};

export function getRuleOutcomeStatus(rule: RuleOutcomeLike): RuleOutcomeStatus {
  if (rule.status) {
    return rule.status;
  }
  if (rule.followed === true) {
    return 'FOLLOWED';
  }
  if (rule.followed === false) {
    return 'VIOLATED';
  }
  return 'NOT_EVALUATED';
}

export function getRuleOutcomeMeta(status: RuleOutcomeStatus): {
  label: string;
  icon: string;
  badgeClass: string;
  textClass: string;
} {
  switch (status) {
    case 'FOLLOWED':
      return {
        label: 'Followed',
        icon: '\u2713',
        badgeClass: 'bg-[var(--color-success)] text-white',
        textClass: 'text-[var(--color-success)]',
      };
    case 'VIOLATED':
      return {
        label: 'Violated',
        icon: '\u2717',
        badgeClass: 'bg-[var(--color-error)] text-white',
        textClass: 'text-[var(--color-error)]',
      };
    case 'NOT_APPLICABLE':
      return {
        label: 'Not Applicable',
        icon: 'i',
        badgeClass: 'bg-[var(--surface-info)] text-[var(--text-brand)] border border-[var(--border-brand)]',
        textClass: 'text-[var(--text-brand)]',
      };
    case 'NOT_EVALUATED':
      return {
        label: 'Not Evaluated',
        icon: '?',
        badgeClass: 'bg-[var(--bg-tertiary)] text-[var(--text-muted)] border border-[var(--border-subtle)]',
        textClass: 'text-[var(--text-muted)]',
      };
  }
}

export function countRuleOutcomes<T extends RuleOutcomeLike>(
  rules: T[],
): RuleOutcomeCounts {
  return rules.reduce<RuleOutcomeCounts>((counts, rule) => {
    const status = getRuleOutcomeStatus(rule);
    if (status === 'FOLLOWED') {
      counts.followed += 1;
      counts.evaluatedCount += 1;
    } else if (status === 'VIOLATED') {
      counts.violated += 1;
      counts.evaluatedCount += 1;
    } else if (status === 'NOT_APPLICABLE') {
      counts.notApplicable += 1;
    } else {
      counts.notEvaluated += 1;
    }
    return counts;
  }, {
    followed: 0,
    violated: 0,
    notApplicable: 0,
    notEvaluated: 0,
    evaluatedCount: 0,
  });
}

export function summarizeRuleOutcomes<T extends RuleOutcomeLike>(
  rules: T[],
): string {
  const counts = countRuleOutcomes(rules);
  const suffixParts: string[] = [];
  if (counts.notApplicable > 0) {
    suffixParts.push(`${counts.notApplicable} not applicable`);
  }
  if (counts.notEvaluated > 0) {
    suffixParts.push(`${counts.notEvaluated} not evaluated`);
  }

  let base = '';
  if (counts.evaluatedCount === 0) {
    base = 'No evaluated rules';
  } else if (counts.violated === 0) {
    base = `All ${counts.evaluatedCount} evaluated rules followed`;
  } else {
    base = `${counts.violated} of ${counts.evaluatedCount} evaluated rules violated`;
  }

  return suffixParts.length > 0 ? `${base} (${suffixParts.join(', ')})` : base;
}

export function sortRuleOutcomes<T extends RuleIdentityLike>(
  rules: T[],
): T[] {
  return [...rules].sort((left, right) => {
    const statusOrder = STATUS_ORDER[getRuleOutcomeStatus(left)] - STATUS_ORDER[getRuleOutcomeStatus(right)];
    if (statusOrder !== 0) {
      return statusOrder;
    }
    const leftRuleId = String(left.rule_id ?? left.ruleId ?? '');
    const rightRuleId = String(right.rule_id ?? right.ruleId ?? '');
    return leftRuleId.localeCompare(rightRuleId);
  });
}
