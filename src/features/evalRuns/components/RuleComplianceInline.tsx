import type { CanonicalThreadRuleOutcome, RuleCompliance } from '@/types';
import {
  getRuleOutcomeMeta,
  getRuleOutcomeStatus,
  sortRuleOutcomes,
  summarizeRuleOutcomes,
} from '../utils/ruleCompliance';

interface Props {
  rules: Array<RuleCompliance | CanonicalThreadRuleOutcome>;
}

export default function RuleComplianceInline({ rules }: Props) {
  if (rules.length === 0) return null;
  const sorted = sortRuleOutcomes(rules);
  const summary = summarizeRuleOutcomes(rules);

  return (
    <div className="space-y-1">
      <p className="text-xs uppercase tracking-wider text-[var(--text-muted)] font-semibold">
        Rule Compliance
        <span className="ml-1.5 normal-case tracking-normal font-normal">
          {`\u2014 ${summary}`}
        </span>
      </p>
      <div className="overflow-x-auto pb-1">
        <table className="w-full text-sm border-collapse" style={{ minWidth: 760 }}>
          <colgroup>
            <col style={{ width: '4rem' }} />
            <col style={{ width: '16rem' }} />
            <col style={{ width: '16rem' }} />
            <col style={{ width: '24rem' }} />
          </colgroup>
          <thead>
            <tr className="border-b border-[var(--border-subtle)]">
              <th className="text-left text-xs text-[var(--text-muted)] font-semibold py-1 px-3 whitespace-nowrap">Status</th>
              <th className="text-left text-xs text-[var(--text-muted)] font-semibold py-1 px-3 whitespace-nowrap">Rule ID</th>
              <th className="text-left text-xs text-[var(--text-muted)] font-semibold py-1 px-3 whitespace-nowrap">Section</th>
              <th className="text-left text-xs text-[var(--text-muted)] font-semibold py-1 px-3 whitespace-nowrap">Evidence</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((rule) => {
              const ruleId = 'rule_id' in rule ? rule.rule_id : rule.ruleId;
              const status = getRuleOutcomeStatus({
                status: rule.status,
                followed: 'followed' in rule ? rule.followed : null,
              });
              const meta = getRuleOutcomeMeta(status);
              return (
                <tr key={ruleId} className="border-b border-[var(--border-subtle)] last:border-b-0">
                  <td className="py-2 px-3 align-top">
                    <span className={`inline-flex items-center justify-center w-4 h-4 rounded-full text-[0.6rem] font-bold ${meta.badgeClass}`}>
                      {meta.icon}
                    </span>
                  </td>
                  <td className={`py-2 px-3 font-semibold whitespace-nowrap align-top ${meta.textClass}`}>
                    {ruleId}
                  </td>
                  <td className="py-2 px-3 text-[var(--text-secondary)] min-w-[14rem] align-top">{rule.section || '\u2014'}</td>
                  <td className="py-2 px-3 text-[var(--text-secondary)] break-words leading-5 min-w-[22rem] align-top">{rule.evidence || '\u2014'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
