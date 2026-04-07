import { Badge, RoleBadge } from '@/components/ui';
import { SchemaTable } from './SchemaTable';
import { extractMetricFields } from '@/features/evals/utils/evaluatorMetadata';
import type { EvalRun, EvaluatorDefinition, RuleCatalogEntry } from '@/types';

interface EvaluatorExpandRowProps {
  evaluator: EvaluatorDefinition;
  rules: RuleCatalogEntry[];
  latestRun?: EvalRun;
}

function summarizeRun(latestRun?: EvalRun): string | null {
  if (!latestRun) {
    return null;
  }
  if (latestRun.status === 'completed') {
    return 'Latest run completed';
  }
  if (latestRun.status === 'running') {
    return 'Latest run in progress';
  }
  if (latestRun.status === 'failed') {
    return latestRun.errorMessage || 'Latest run failed';
  }
  return `Latest run ${latestRun.status}`;
}

export function EvaluatorExpandRow({
  evaluator,
  rules,
  latestRun,
}: EvaluatorExpandRowProps) {
  const linkedRules = rules.filter((rule) => evaluator.linkedRuleIds?.includes(rule.ruleId));
  const runSummary = summarizeRun(latestRun);
  const metricFields = extractMetricFields(evaluator, latestRun);

  return (
    <div className="space-y-4 rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)]/30 p-4">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <section className="space-y-2">
          <div className="flex items-center gap-2">
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">Prompt</h4>
            {runSummary ? <Badge variant="info">{runSummary}</Badge> : null}
          </div>
          <pre className="whitespace-pre-wrap rounded-[8px] border border-[var(--border-default)] bg-[var(--bg-primary)] p-3 text-xs text-[var(--text-secondary)]">
            {evaluator.prompt}
          </pre>
        </section>

        <section className="space-y-2">
          <h4 className="text-sm font-semibold text-[var(--text-primary)]">Linked Rules</h4>
          {linkedRules.length === 0 ? (
            <p className="text-sm text-[var(--text-secondary)]">No rules linked.</p>
          ) : (
            <div className="space-y-2">
              {linkedRules.map((rule) => (
                <div
                  key={rule.ruleId}
                  className="rounded-[8px] border border-[var(--border-default)] bg-[var(--bg-primary)] p-3"
                >
                  <div className="flex items-center gap-2">
                    <Badge variant="primary">{rule.ruleId}</Badge>
                    {rule.section ? <Badge variant="neutral">{rule.section}</Badge> : null}
                  </div>
                  <p className="mt-2 text-sm text-[var(--text-primary)]">{rule.ruleText}</p>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      <section className="space-y-2">
        <div className="flex items-center gap-2">
          <h4 className="text-sm font-semibold text-[var(--text-primary)]">Schema</h4>
          {evaluator.outputSchema.some((field) => field.role) ? null : (
            <Badge variant="warning">Legacy schema</Badge>
          )}
        </div>
        <SchemaTable fields={evaluator.outputSchema} readOnly />
        <div className="flex flex-wrap gap-2">
          {evaluator.outputSchema.map((field) => (
            <RoleBadge key={`${field.key}-${field.role ?? 'detail'}`} role={field.role ?? 'detail'} />
          ))}
        </div>
      </section>

      {metricFields.length > 0 && (
        <section className="space-y-2">
          <h4 className="text-sm font-semibold text-[var(--text-primary)]">Latest Run Metrics</h4>
          <div className="flex flex-wrap gap-2">
            {metricFields.map(({ key, label, value, type }) => (
              <div
                key={key}
                className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 min-w-[120px]"
              >
                <span className="text-[11px] font-medium text-[var(--text-muted)] block truncate">{label}</span>
                <span className="text-sm font-semibold text-[var(--text-primary)]">
                  {type === 'number' && typeof value === 'number' ? value.toFixed(2) : String(value)}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
