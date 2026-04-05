import type { EvaluatorDefinition, EvaluatorOutputField } from '@/types';

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
