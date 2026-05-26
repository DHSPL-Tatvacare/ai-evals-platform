import { describe, it, expect } from 'vitest';
import { pickLiveRun } from './useLiveWorkflowRun';
import type { WorkflowRun } from '@/features/orchestration/types';

const run = (id: string, status: WorkflowRun['status']): WorkflowRun =>
  ({ id, status } as WorkflowRun);

describe('pickLiveRun', () => {
  it('returns the newest active run (list is newest-first)', () => {
    expect(pickLiveRun([run('c', 'running'), run('b', 'completed')])?.id).toBe('c');
  });
  it('skips terminal runs', () => {
    expect(pickLiveRun([run('c', 'completed'), run('b', 'failed')])).toBeNull();
  });
  it('treats pending and waiting as active', () => {
    expect(pickLiveRun([run('c', 'waiting')])?.id).toBe('c');
  });
  it('handles empty / undefined', () => {
    expect(pickLiveRun([])).toBeNull();
    expect(pickLiveRun(undefined)).toBeNull();
  });
});
