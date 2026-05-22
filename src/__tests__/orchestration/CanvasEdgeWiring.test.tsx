/**
 * Phase 3 — Canvas edge-interaction wiring.
 *
 * Canvas hands React Flow the delete key, the connect guard, and the
 * reconnect handler; the integrity logic lives in the store. jsdom can't
 * fire real React Flow pointer interactions, so we mock the `ReactFlow`
 * component to capture the props Canvas passes and invoke the handlers
 * directly — proving the canvas wires Delete / connect / reconnect to the
 * store guards (and never the silent `output_id:'default'` path).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render } from '@testing-library/react';
import type {
  Connection,
  Edge,
  EdgeChange,
  ReactFlowProps,
} from '@xyflow/react';

import { Canvas } from '@/features/orchestration/components/Canvas';
import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import { getEdgeOutputId } from '@/features/orchestration/types';

let capturedProps: ReactFlowProps | null = null;

vi.mock('@xyflow/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@xyflow/react')>();
  return {
    ...actual,
    ReactFlow: (props: ReactFlowProps) => {
      capturedProps = props;
      return null;
    },
  };
});

describe('Canvas edge-interaction wiring', () => {
  beforeEach(() => {
    capturedProps = null;
    useWorkflowBuilderStore.getState().reset();
    useWorkflowBuilderStore.getState().setViewMode('edit');
  });

  it('binds Delete and Backspace as the delete keys', () => {
    render(<Canvas />);
    expect(capturedProps?.deleteKeyCode).toEqual(['Delete', 'Backspace']);
  });

  it('Delete on a selected edge removes it from the store', () => {
    const s = useWorkflowBuilderStore.getState();
    s.addEdge({ id: 'e1', source: 'a', target: 'b', output_id: 'success' });
    render(<Canvas />);
    const change: EdgeChange = { id: 'e1', type: 'remove' };
    capturedProps?.onEdgesChange?.([change]);
    expect(useWorkflowBuilderStore.getState().edges).toHaveLength(0);
  });

  it('onConnect rejects a connection with no sourceHandle (no default edge)', () => {
    render(<Canvas />);
    const conn: Connection = {
      source: 'a',
      target: 'b',
      sourceHandle: null,
      targetHandle: null,
    };
    capturedProps?.onConnect?.(conn);
    expect(useWorkflowBuilderStore.getState().edges).toHaveLength(0);
  });

  it('onConnect from a branch handle writes that branch output_id', () => {
    render(<Canvas />);
    const conn: Connection = {
      source: 'cond',
      target: 'b',
      sourceHandle: 'vip',
      targetHandle: null,
    };
    capturedProps?.onConnect?.(conn);
    const edges = useWorkflowBuilderStore.getState().edges;
    expect(edges).toHaveLength(1);
    expect(getEdgeOutputId(edges[0])).toBe('vip');
  });

  it('onReconnect re-points an existing edge through the store', () => {
    const s = useWorkflowBuilderStore.getState();
    s.addEdge({ id: 'e1', source: 'a', target: 'b', output_id: 'success' });
    render(<Canvas />);
    const oldEdge = { id: 'e1', source: 'a', target: 'b' } as Edge;
    const conn: Connection = {
      source: 'a',
      target: 'c',
      sourceHandle: 'failed',
      targetHandle: null,
    };
    capturedProps?.onReconnect?.(oldEdge, conn);
    const edges = useWorkflowBuilderStore.getState().edges;
    expect(edges).toHaveLength(1);
    expect(edges[0].target).toBe('c');
    expect(getEdgeOutputId(edges[0])).toBe('failed');
  });
});
