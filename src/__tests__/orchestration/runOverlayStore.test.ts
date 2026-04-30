import { describe, expect, it, beforeEach } from 'vitest';

import { useRunOverlayStore } from '@/features/orchestration/store/runOverlayStore';

describe('runOverlayStore', () => {
  beforeEach(() => useRunOverlayStore.getState().reset());

  it('node_step.started records running status with cohort size', () => {
    useRunOverlayStore.getState().applyEvent({
      type: 'node_step.started',
      node_id: 'n1',
      input_cohort_size: 7,
    });
    const node = useRunOverlayStore.getState().byNodeId.n1;
    expect(node).toBeDefined();
    expect(node.status).toBe('running');
    expect(node.inputCohortSize).toBe(7);
  });

  it('node_step.completed overrides running and preserves cohort size', () => {
    useRunOverlayStore.getState().applyEvent({
      type: 'node_step.started',
      node_id: 'n1',
      input_cohort_size: 5,
    });
    useRunOverlayStore.getState().applyEvent({
      type: 'node_step.completed',
      node_id: 'n1',
      outputs_summary: { x: 1 },
    });
    const node = useRunOverlayStore.getState().byNodeId.n1;
    expect(node.status).toBe('completed');
    expect(node.outputsSummary).toEqual({ x: 1 });
    expect(node.inputCohortSize).toBe(5);
  });

  it('node_step.failed records error', () => {
    useRunOverlayStore.getState().applyEvent({
      type: 'node_step.failed',
      node_id: 'n1',
      error: 'RuntimeError(boom)',
    });
    const node = useRunOverlayStore.getState().byNodeId.n1;
    expect(node.status).toBe('failed');
    expect(node.error).toBe('RuntimeError(boom)');
  });

  it('run lifecycle events update runStatus', () => {
    useRunOverlayStore.getState().applyEvent({ type: 'run.started' });
    expect(useRunOverlayStore.getState().runStatus).toBe('running');
    useRunOverlayStore.getState().applyEvent({ type: 'run.completed', status: 'completed' });
    expect(useRunOverlayStore.getState().runStatus).toBe('completed');
  });

  it('run.failed sets failed', () => {
    useRunOverlayStore.getState().applyEvent({ type: 'run.failed', error: 'x' });
    expect(useRunOverlayStore.getState().runStatus).toBe('failed');
  });

  it('unknown events are ignored', () => {
    useRunOverlayStore.getState().applyEvent({ type: 'random.unknown', node_id: 'n1' });
    expect(useRunOverlayStore.getState().byNodeId).toEqual({});
  });

  it('reset clears all state including stream status', () => {
    useRunOverlayStore.getState().setStreamStatus('open');
    useRunOverlayStore.getState().applyEvent({ type: 'node_step.started', node_id: 'n1' });
    useRunOverlayStore.getState().reset();
    expect(useRunOverlayStore.getState().byNodeId).toEqual({});
    expect(useRunOverlayStore.getState().streamStatus).toBe('idle');
    expect(useRunOverlayStore.getState().runStatus).toBe('pending');
  });
});
