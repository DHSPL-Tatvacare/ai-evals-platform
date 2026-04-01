import { useState } from 'react';
import type {
  CanonicalThreadEvaluation,
  RuleCompliance,
  RuleOutcomeStatus,
  CorrectnessEvaluation,
  EfficiencyEvaluation,
} from '@/types/evalRuns';
import { cn } from '@/utils';
import {
  getRuleOutcomeMeta,
  getRuleOutcomeStatus,
  sortRuleOutcomes,
  summarizeRuleOutcomes,
} from '../../utils/ruleCompliance';

type Filter = 'ALL' | RuleOutcomeStatus;

interface AggregatedRule {
  ruleId: string;
  section: string;
  evidence: string;
  status: RuleOutcomeStatus;
  followed: boolean | null;
  source: string;
}

interface Props {
  efficiencyEvaluation?: EfficiencyEvaluation | null;
  correctnessEvaluations?: CorrectnessEvaluation[];
  canonicalThread?: CanonicalThreadEvaluation | null;
  rules?: RuleCompliance[];
  sourceLabel?: string;
}

const STATUS_PRIORITY: Record<RuleOutcomeStatus, number> = {
  VIOLATED: 0,
  FOLLOWED: 1,
  NOT_APPLICABLE: 2,
  NOT_EVALUATED: 3,
};

function normalizeLegacyRule(rule: RuleCompliance, source: string): AggregatedRule {
  const status = getRuleOutcomeStatus(rule);
  return {
    ruleId: rule.rule_id,
    section: rule.section,
    evidence: rule.evidence,
    status,
    followed: status === 'FOLLOWED' ? true : status === 'VIOLATED' ? false : null,
    source,
  };
}

function aggregateLegacyRules(
  efficiencyEvaluation?: EfficiencyEvaluation | null,
  correctnessEvaluations?: CorrectnessEvaluation[],
): AggregatedRule[] {
  const ruleMap = new Map<string, AggregatedRule>();

  if (efficiencyEvaluation?.rule_compliance) {
    for (const rule of efficiencyEvaluation.rule_compliance) {
      const normalized = normalizeLegacyRule(rule, 'Efficiency');
      const existing = ruleMap.get(normalized.ruleId);
      if (!existing || STATUS_PRIORITY[normalized.status] < STATUS_PRIORITY[existing.status]) {
        ruleMap.set(normalized.ruleId, normalized);
      }
    }
  }

  for (let index = 0; index < (correctnessEvaluations?.length ?? 0); index += 1) {
    const evaluation = correctnessEvaluations?.[index];
    if (!evaluation?.rule_compliance) {
      continue;
    }
    for (const rule of evaluation.rule_compliance) {
      const normalized = normalizeLegacyRule(rule, `Correctness #${index + 1}`);
      const existing = ruleMap.get(normalized.ruleId);
      if (!existing || STATUS_PRIORITY[normalized.status] < STATUS_PRIORITY[existing.status]) {
        ruleMap.set(normalized.ruleId, normalized);
      }
    }
  }

  return sortRuleOutcomes(
    Array.from(ruleMap.values()).map((rule) => ({
      rule_id: rule.ruleId,
      section: rule.section,
      evidence: rule.evidence,
      status: rule.status,
      followed: rule.followed,
      source: rule.source,
    })),
  ).map((rule) => ({
    ruleId: rule.rule_id,
    section: rule.section,
    evidence: rule.evidence,
    status: rule.status,
    followed: rule.followed,
    source: (rule as typeof rule & { source: string }).source,
  }));
}

function rulesFromCanonical(canonicalThread: CanonicalThreadEvaluation): AggregatedRule[] {
  return canonicalThread.derived.canonicalRuleOutcomes.map((rule) => ({
    ruleId: rule.ruleId,
    section: rule.section ?? '',
    evidence: rule.evidence,
    status: rule.status,
    followed: rule.followed,
    source: rule.sources.length > 0
      ? rule.sources.map((source) => source.sourceLabel).join(', ')
      : 'Overall',
  }));
}

export default function RuleComplianceTab({
  efficiencyEvaluation,
  correctnessEvaluations,
  canonicalThread,
  rules,
  sourceLabel = 'Overall',
}: Props) {
  const [filter, setFilter] = useState<Filter>('ALL');

  const allRules: AggregatedRule[] = rules
    ? sortRuleOutcomes(rules).map((rule) => {
      const status = getRuleOutcomeStatus(rule);
      return {
        ruleId: rule.rule_id,
        section: rule.section,
        evidence: rule.evidence,
        status,
        followed: status === 'FOLLOWED' ? true : status === 'VIOLATED' ? false : null,
        source: sourceLabel,
      };
    })
    : canonicalThread
      ? rulesFromCanonical(canonicalThread)
      : aggregateLegacyRules(efficiencyEvaluation, correctnessEvaluations);

  if (allRules.length === 0) {
    return (
      <p className="text-sm text-[var(--text-muted)] py-4 text-center">
        No rule compliance data available.
      </p>
    );
  }

  const filtered = filter === 'ALL'
    ? allRules
    : allRules.filter((rule) => rule.status === filter);

  const counts = {
    FOLLOWED: allRules.filter((rule) => rule.status === 'FOLLOWED').length,
    VIOLATED: allRules.filter((rule) => rule.status === 'VIOLATED').length,
    NOT_APPLICABLE: allRules.filter((rule) => rule.status === 'NOT_APPLICABLE').length,
    NOT_EVALUATED: allRules.filter((rule) => rule.status === 'NOT_EVALUATED').length,
  };

  return (
    <div className="flex flex-col h-full min-h-0 px-4">
      <div className="flex flex-wrap gap-1 pb-2 shrink-0">
        {([
          { key: 'ALL' as Filter, label: 'All', count: allRules.length },
          { key: 'VIOLATED' as Filter, label: 'Violations', count: counts.VIOLATED },
          { key: 'FOLLOWED' as Filter, label: 'Followed', count: counts.FOLLOWED },
          { key: 'NOT_APPLICABLE' as Filter, label: 'Not Applicable', count: counts.NOT_APPLICABLE },
          { key: 'NOT_EVALUATED' as Filter, label: 'Not Evaluated', count: counts.NOT_EVALUATED },
        ]).map((item) => (
          item.count === 0 && item.key !== 'ALL' ? null : (
            <button
              key={item.key}
              onClick={() => setFilter(item.key)}
              className={cn(
                'px-2 py-0.5 text-xs rounded-full border transition-colors',
                filter === item.key
                  ? 'border-[var(--border-brand)] bg-[var(--surface-info)] text-[var(--text-brand)]'
                  : 'border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]',
              )}
            >
              {item.label} ({item.count})
            </button>
          )
        ))}
      </div>

      <p className="text-xs text-[var(--text-muted)] pb-3 shrink-0">
        {summarizeRuleOutcomes(allRules.map((rule) => ({ status: rule.status, followed: rule.followed })))}
      </p>

      <div className="flex-1 min-h-0 overflow-y-auto">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" style={{ minWidth: 720 }}>
            <thead className="sticky top-0 bg-[var(--bg-primary)] z-10">
              <tr className="border-b border-[var(--border-subtle)]">
                <th className="text-center text-xs text-[var(--text-muted)] font-semibold py-1.5 px-2 w-16">Status</th>
                <th className="text-left text-xs text-[var(--text-muted)] font-semibold py-1.5 px-2 whitespace-nowrap">Rule ID</th>
                <th className="text-left text-xs text-[var(--text-muted)] font-semibold py-1.5 px-2 whitespace-nowrap">Section in Kaira Prompt</th>
                <th className="text-left text-xs text-[var(--text-muted)] font-semibold py-1.5 px-2 w-36">Source</th>
                <th className="text-left text-xs text-[var(--text-muted)] font-semibold py-1.5 px-2">Evidence</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((rule) => {
                const meta = getRuleOutcomeMeta(rule.status);
                return (
                  <tr key={rule.ruleId} className="border-b border-[var(--border-subtle)]">
                    <td className="py-1.5 px-2 text-center">
                      <span className={`inline-flex items-center justify-center min-w-[96px] px-2 py-0.5 rounded-full text-[0.65rem] font-semibold ${meta.badgeClass}`}>
                        {meta.label}
                      </span>
                    </td>
                    <td className={`py-1.5 px-2 font-semibold ${meta.textClass}`}>
                      {rule.ruleId}
                    </td>
                    <td className="py-1.5 px-2 text-[var(--text-secondary)] max-w-[180px]">
                      <span className="block text-xs bg-[var(--bg-primary)] border border-[var(--border-subtle)] px-1.5 py-px rounded-full truncate" title={rule.section || ''}>
                        {rule.section || '\u2014'}
                      </span>
                    </td>
                    <td className="py-1.5 px-2 text-[var(--text-muted)] text-xs">
                      {rule.source}
                    </td>
                    <td className="py-1.5 px-2 text-[var(--text-secondary)] text-xs">
                      {rule.evidence || '\u2014'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
