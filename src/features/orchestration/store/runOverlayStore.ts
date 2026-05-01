import { create } from 'zustand';

import type { NodeOverlayStatus } from '@/features/orchestration/components/CustomNode';

export interface NodeStepState {
  status: NodeOverlayStatus;
  inputCohortSize?: number;
  outputsSummary?: Record<string, unknown>;
  error?: string;
}

export type RunStreamStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'error';

interface RunOverlayState {
  /** Lifecycle status of the SSE stream itself (NOT the run). */
  streamStatus: RunStreamStatus;
  /** Lifecycle status of the run as reported by run.* events. */
  runStatus: 'pending' | 'running' | 'waiting' | 'completed' | 'failed' | 'cancelled';
  /** Last error string reported by `run.failed`, used by toast surface. */
  runError: string | null;
  /** Per-node aggregated state (latest event wins). */
  byNodeId: Record<string, NodeStepState>;

  reset(): void;
  setStreamStatus(s: RunStreamStatus): void;
  applyEvent(event: { type: string; [k: string]: unknown }): void;
}

export const useRunOverlayStore = create<RunOverlayState>((set) => ({
  streamStatus: 'idle',
  runStatus: 'pending',
  runError: null,
  byNodeId: {},

  reset: () =>
    set({
      streamStatus: 'idle',
      runStatus: 'pending',
      runError: null,
      byNodeId: {},
    }),

  setStreamStatus: (s) => set({ streamStatus: s }),

  applyEvent: (e) =>
    set((s) => {
      const nid = e.node_id as string | undefined;
      switch (e.type) {
        case 'run.started':
          return { runStatus: 'running' };
        case 'run.completed': {
          const status = (e.status as RunOverlayState['runStatus']) ?? 'completed';
          return { runStatus: status };
        }
        case 'run.failed':
          return {
            runStatus: 'failed',
            runError: typeof e.error === 'string' ? e.error : null,
          };
        case 'node_step.started':
          if (!nid) return {};
          return {
            byNodeId: {
              ...s.byNodeId,
              [nid]: {
                status: 'running',
                inputCohortSize: e.input_cohort_size as number | undefined,
              },
            },
          };
        case 'node_step.completed':
          if (!nid) return {};
          return {
            byNodeId: {
              ...s.byNodeId,
              [nid]: {
                status: 'completed',
                outputsSummary: e.outputs_summary as Record<string, unknown> | undefined,
                inputCohortSize: s.byNodeId[nid]?.inputCohortSize,
              },
            },
          };
        case 'node_step.failed':
          if (!nid) return {};
          return {
            byNodeId: {
              ...s.byNodeId,
              [nid]: {
                status: 'failed',
                error: typeof e.error === 'string' ? e.error : undefined,
                inputCohortSize: s.byNodeId[nid]?.inputCohortSize,
              },
            },
          };
        default:
          return {};
      }
    }),
}));
