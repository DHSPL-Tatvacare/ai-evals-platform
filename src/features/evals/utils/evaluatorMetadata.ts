import type { EvaluatorDefinition, EvaluatorOutputField, EvalRun } from '@/types';

const SYSTEM_TENANT_ID = '00000000-0000-0000-0000-000000000001';
const SYSTEM_USER_ID = '00000000-0000-0000-0000-000000000002';

export function getEvaluatorMainMetricField(
  evaluator: Pick<EvaluatorDefinition, 'outputSchema'>,
): EvaluatorOutputField | undefined {
  return evaluator.outputSchema.find((field) => field.isMainMetric);
}

export function evaluatorShowsInHeader(
  evaluator: Pick<EvaluatorDefinition, 'outputSchema'>,
): boolean {
  const mainMetricField = getEvaluatorMainMetricField(evaluator);
  return mainMetricField?.displayMode === 'header';
}

export function setEvaluatorHeaderVisibility(
  outputSchema: EvaluatorOutputField[],
  showInHeader: boolean,
): EvaluatorOutputField[] {
  return outputSchema.map((field) => {
    if (!field.isMainMetric) {
      return field;
    }

    return {
      ...field,
      displayMode: showInHeader ? 'header' : 'card',
    };
  });
}

export function isSystemEvaluator(
  evaluator: Pick<EvaluatorDefinition, 'tenantId' | 'userId'>,
): boolean {
  return evaluator.tenantId === SYSTEM_TENANT_ID && evaluator.userId === SYSTEM_USER_ID;
}

/**
 * Extract the main metric display value from a completed eval run result.
 * Returns null if no main metric is configured or run has no output.
 */
export function extractMainMetricValue(
  evaluator: Pick<EvaluatorDefinition, 'outputSchema'>,
  run?: Pick<EvalRun, 'status' | 'result'>,
): { label: string; value: unknown; type: string; field: EvaluatorOutputField } | null {
  if (!run || run.status !== 'completed') return null;
  const field = getEvaluatorMainMetricField(evaluator);
  if (!field) return null;
  const output = (run.result as Record<string, unknown> | undefined)?.output as Record<string, unknown> | undefined;
  const value = output?.[field.key];
  if (value === undefined || value === null) return null;
  return { label: field.label ?? field.key, value, type: field.type, field };
}

/**
 * Extract all metric-role field values from a completed eval run result.
 */
export function extractMetricFields(
  evaluator: Pick<EvaluatorDefinition, 'outputSchema'>,
  run?: Pick<EvalRun, 'status' | 'result'>,
): Array<{ key: string; label: string; value: unknown; type: string; field: EvaluatorOutputField }> {
  if (!run || run.status !== 'completed') return [];
  const output = (run.result as Record<string, unknown> | undefined)?.output as Record<string, unknown> | undefined;
  if (!output) return [];
  return evaluator.outputSchema
    .filter((f) => f.role === 'metric')
    .map((field) => ({
      key: field.key,
      label: field.label ?? field.key,
      value: output[field.key],
      type: field.type,
      field,
    }))
    .filter((m) => m.value !== undefined && m.value !== null);
}
