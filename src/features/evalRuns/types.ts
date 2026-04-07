export type RunType = 'batch' | 'adversarial' | 'thread' | 'evaluation' | 'custom' | 'call_quality';

export const RUN_TYPE_CONFIG: Record<RunType, { color: string; label: string }> = {
  batch:        { color: 'var(--color-type-batch)',        label: 'BATCH' },
  adversarial:  { color: 'var(--color-type-adversarial)',  label: 'ADVERSARIAL' },
  thread:       { color: 'var(--color-type-thread)',       label: 'THREAD' },
  evaluation:   { color: 'var(--color-type-evaluation)',   label: 'EVALUATION' },
  custom:       { color: 'var(--color-type-custom)',       label: 'CUSTOM' },
  call_quality: { color: 'var(--color-type-call-quality)', label: 'CALL QUALITY' },
};
