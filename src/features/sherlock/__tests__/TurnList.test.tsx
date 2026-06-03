import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { create } from 'zustand';

import { TurnList } from '@/features/sherlock/TurnList';
import type { ApplyCanvasPatchResult } from '@/features/orchestration/copilot/canvasPatchApplier';
import type {
  AssistantTextPart,
  CanvasPatchPart,
  ChartPart,
  SherlockPart,
  StepFinishPart,
  StepStartPart,
  SubtaskPart,
  SubtaskResult,
  UserMessagePart,
} from '@/features/sherlock/generated/sherlockContract';

const landCanvasPatch = vi.fn<
  (partId: string, patch: unknown) => Promise<ApplyCanvasPatchResult | undefined>
>();

interface MockStoreState {
  landCanvasPatch: typeof landCanvasPatch;
  applyInverse: () => void;
  markChanged: (ids: readonly string[]) => void;
  paletteCatalog: unknown[];
  canvasEdits: Record<string, { result: ApplyCanvasPatchResult; changedNodeIds: string[] }>;
}

const useMockBuilderStore = create<MockStoreState>(() => ({
  landCanvasPatch,
  applyInverse: () => {},
  markChanged: () => {},
  paletteCatalog: [],
  canvasEdits: {},
}));

vi.mock('@/features/orchestration/store/workflowBuilderStore', () => ({
  useWorkflowBuilderStore: (selector: (s: MockStoreState) => unknown) =>
    useMockBuilderStore(selector),
}));

const BASE = { chat_session_id: 'sess-1', created_at: 0 } as const;

const stepStart: StepStartPart = { ...BASE, id: 'ss', seq: 0, type: 'step_start', turn_id: 'turn-1' };
const userMsg: UserMessagePart = { ...BASE, id: 'um', seq: 1, type: 'user_message', text: 'how many leads?' };

function dataSubtask(seq: number, id: string, state: SubtaskPart['state']): SubtaskPart {
  return {
    ...BASE,
    id,
    seq,
    type: 'subtask',
    specialist: 'data_specialist',
    call_id: `call_${id}`,
    brief: { question: 'count leads', scope: { tenant_id: 't', app_id: 'a', user_id: 'u' }, prior_attempts: [], retry_hint: null },
    state,
  };
}
function completed(result: SubtaskResult): SubtaskPart['state'] {
  return { status: 'completed', started_at: 0, ended_at: 200, result };
}

const answer: AssistantTextPart = { ...BASE, id: 'at', seq: 4, type: 'assistant_text', text: '7,201 leads', final: true };
const chart: ChartPart = {
  ...BASE,
  id: 'ch',
  seq: 5,
  type: 'chart',
  artifact: {
    kind: 'kpi',
    payload: { kind: 'kpi', kpi: { label: 'Leads', value: 7201, format: 'integer' }, title: 'Leads', source_question: '', sql_query: '' },
  },
};
const stepFinish: StepFinishPart = {
  ...BASE,
  id: 'sf',
  seq: 6,
  type: 'step_finish',
  turn_id: 'turn-1',
  status: 'done',
  last_response_id: null,
  tokens_in: 1,
  tokens_out: 1,
};

describe('TurnList', () => {
  const settledParts: SherlockPart[] = [
    stepStart,
    userMsg,
    dataSubtask(2, 'st-data', completed({ status: 'ok', summary: 'Counted leads', sql: 'select count(*)', row_count: 1 })),
    chart,
    answer,
    stepFinish,
  ];

  it('renders the user question and the assistant answer', () => {
    render(<TurnList parts={settledParts} appId="inside-sales" sessionId={null} streaming={false} onRetry={() => {}} />);
    expect(screen.getByText('how many leads?')).toBeTruthy();
    expect(screen.getByText('7,201 leads')).toBeTruthy();
  });

  it('renders specialist runs as a collapsed summary that resolves (no perpetual spinner)', () => {
    const { container } = render(
      <TurnList parts={settledParts} appId="inside-sales" sessionId={null} streaming={false} onRetry={() => {}} />,
    );
    expect(container.querySelector('[data-part-type="specialist-group"]')).not.toBeNull();
    expect(screen.getByText(/Consulted Titan Mnemosyne, the archivist/i)).toBeTruthy();
    expect(screen.queryByText(/Consulting/i)).toBeNull();
  });

  it('routes a KPI artifact into a prominent number card', () => {
    render(<TurnList parts={settledParts} appId="inside-sales" sessionId={null} streaming={false} onRetry={() => {}} />);
    expect(screen.getByText('7,201')).toBeTruthy();
  });

  it('holds the chart until the turn settles — never mid-consultation', () => {
    // live turn: a chart part has arrived while a specialist is still consulting
    const live: SherlockPart[] = [
      stepStart,
      userMsg,
      dataSubtask(2, 'st-data', { status: 'running', started_at: 0 }),
      chart,
    ];
    const { rerender } = render(
      <TurnList parts={live} appId="inside-sales" sessionId={null} streaming onRetry={() => {}} />,
    );
    // chart must NOT show while live (KPI value hidden)
    expect(screen.queryByText('7,201')).toBeNull();
    // once settled, the chart renders
    rerender(<TurnList parts={settledParts} appId="inside-sales" sessionId={null} streaming={false} onRetry={() => {}} />);
    expect(screen.getByText('7,201')).toBeTruthy();
  });

  it('lets the consulting row be the single live line — no standalone glass while a specialist runs', () => {
    const inflight: SherlockPart[] = [
      stepStart,
      userMsg,
      dataSubtask(2, 'st-data', { status: 'running', started_at: 0 }),
    ];
    const { container } = render(
      <TurnList parts={inflight} appId="inside-sales" sessionId={null} streaming onRetry={() => {}} />,
    );
    // the specialist group narrates; the standalone thinking glass yields to it
    expect(container.querySelector('[data-testid="sherlock-thinking"]')).toBeNull();
    // the expanded row reads "consulting…", honestly from state, and is the one shimmer
    expect(screen.getByText(/consulting…/i)).toBeTruthy();
    expect(container.querySelectorAll('[class*="chat-widget-shimmer"]').length).toBe(1);
  });

  it('resolves every specialist from its own state — no perpetual spinner on a settled turn', () => {
    // query_synthesis emits no tool; its subtask still carries a completed state.
    const qs: SubtaskPart = {
      ...BASE,
      id: 'st-qs',
      seq: 2,
      type: 'subtask',
      specialist: 'query_synthesis_specialist',
      call_id: 'call_qs',
      brief: { question: 'shape the query', scope: { tenant_id: 't', app_id: 'a', user_id: 'u' }, prior_attempts: [], retry_hint: null },
      state: completed({ status: 'ok', summary: '' }),
    };
    const settled: SherlockPart[] = [
      stepStart,
      userMsg,
      qs,
      dataSubtask(3, 'st-data', completed({ status: 'ok', summary: 'ok', sql: 'select 1', row_count: 13 })),
      answer,
      stepFinish,
    ];
    render(<TurnList parts={settled} appId="inside-sales" sessionId={null} streaming={false} onRetry={() => {}} />);
    expect(screen.queryByText(/Consulting/i)).toBeNull();
    expect(screen.getByText(/Consulted 2 Titans/i)).toBeTruthy();
  });
});

function canvasPart(id: string): CanvasPatchPart {
  return {
    ...BASE,
    id,
    seq: 5,
    type: 'canvas_patch',
    patch: {
      workflow_id: 'wf-1',
      version_id: null,
      base_data_hash: 'h0',
      rationale: 'wire the flow',
      ops: [
        { op: 'add_node', node_id: 'n1', payload: { node_type: 'voice.place_call', config: {} } },
      ],
    },
  };
}

describe('TurnList canvas_patch bridge', () => {
  beforeEach(() => {
    landCanvasPatch.mockReset();
    useMockBuilderStore.setState({
      landCanvasPatch,
      applyInverse: () => {},
      markChanged: () => {},
      paletteCatalog: [],
      canvasEdits: {},
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  function partsWith(part: CanvasPatchPart): SherlockPart[] {
    return [stepStart, userMsg, part, answer, stepFinish];
  }

  it('renders the canvas-change card and lands the patch exactly once across a re-render', () => {
    const applied: ApplyCanvasPatchResult = {
      kind: 'applied',
      opsApplied: 1,
      addedNodeIds: ['n1'],
      editedNodeIds: [],
      removedNodeIds: [],
      connectEdgeIds: [],
      rationale: 'wire the flow',
      inverse: [],
    };
    landCanvasPatch.mockImplementation(async (partId) => {
      useMockBuilderStore.setState((s) => ({
        canvasEdits: { ...s.canvasEdits, [partId]: { result: applied, changedNodeIds: ['n1'] } },
      }));
      return applied;
    });

    const part = canvasPart('cp-1');
    const { container, rerender } = render(
      <TurnList parts={partsWith(part)} appId="inside-sales" sessionId={null} streaming={false} onRetry={() => {}} />,
    );
    rerender(
      <TurnList parts={partsWith(part)} appId="inside-sales" sessionId={null} streaming={false} onRetry={() => {}} />,
    );

    expect(container.querySelector('[data-part-type="canvas_patch"]')).not.toBeNull();
    expect(landCanvasPatch).toHaveBeenCalledTimes(1);
    expect(landCanvasPatch).toHaveBeenCalledWith('cp-1', part.patch);
  });

  it('maps an applied result to the applied variant', async () => {
    const applied: ApplyCanvasPatchResult = {
      kind: 'applied',
      opsApplied: 1,
      addedNodeIds: ['n1'],
      editedNodeIds: [],
      removedNodeIds: [],
      connectEdgeIds: [],
      rationale: 'wire the flow',
      inverse: [],
    };
    landCanvasPatch.mockImplementation(async (partId) => {
      useMockBuilderStore.setState((s) => ({
        canvasEdits: { ...s.canvasEdits, [partId]: { result: applied, changedNodeIds: ['n1'] } },
      }));
      return applied;
    });
    const { container } = render(
      <TurnList parts={partsWith(canvasPart('cp-2'))} appId="inside-sales" sessionId={null} streaming={false} onRetry={() => {}} />,
    );
    await act(async () => {});
    expect(container.querySelector('[data-variant="applied"]')).not.toBeNull();
  });

  // Non-applied kinds: the real store returns the result but records NO
  // canvasEdits entry, so the bridge must derive the variant from the RETURN
  // value. Drive the mock purely through the resolved value here.
  it('maps a hash_mismatch result to the conflict variant', async () => {
    landCanvasPatch.mockResolvedValue({ kind: 'hash_mismatch', rationale: 'drift' });
    const { container } = render(
      <TurnList parts={partsWith(canvasPart('cp-3'))} appId="inside-sales" sessionId={null} streaming={false} onRetry={() => {}} />,
    );
    await act(async () => {});
    expect(container.querySelector('[data-variant="conflict"]')).not.toBeNull();
  });
});
