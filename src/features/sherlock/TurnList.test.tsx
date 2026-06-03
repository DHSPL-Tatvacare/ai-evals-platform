import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { create } from 'zustand';

import { TurnList } from '@/features/sherlock/TurnList';
import type { ApplyCanvasPatchResult } from '@/features/orchestration/copilot/canvasPatchApplier';
import type {
  ErrorPart,
  SherlockPart,
  StepFinishPart,
  StepStartPart,
  SubtaskPart,
  UserMessagePart,
} from '@/features/sherlock/generated/sherlockContract';

const SHIMMER_SELECTOR = '[class*="chat-widget-shimmer"]';

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

const errorPart: ErrorPart = {
  ...BASE,
  id: 'err',
  seq: 2,
  type: 'error',
  message: 'The data specialist timed out reaching the warehouse.',
  source: 'data_specialist',
  recoverable: true,
};

const failedFinish: StepFinishPart = {
  ...BASE,
  id: 'sf',
  seq: 3,
  type: 'step_finish',
  turn_id: 'turn-1',
  status: 'error',
  last_response_id: null,
  tokens_in: 1,
  tokens_out: 1,
};

describe('TurnList error region collapse', () => {
  const failedParts: SherlockPart[] = [stepStart, userMsg, errorPart, failedFinish];

  it('renders EXACTLY ONE error region with the real message and a Retry control', () => {
    const onRetry = vi.fn();
    const { container } = render(
      <TurnList parts={failedParts} appId="inside-sales" sessionId={null} streaming={false} onRetry={onRetry} />,
    );

    // exactly one error region (no banner + pill + card trio)
    const regions = container.querySelectorAll('[data-part-type="error"]');
    expect(regions.length).toBe(1);

    // the region carries the real error message, not just the status word
    expect(screen.getByText('The data specialist timed out reaching the warehouse.')).toBeTruthy();

    // the region owns the Retry control
    const retry = screen.getByRole('button', { name: /retry/i });
    expect(retry).toBeTruthy();
    expect(regions[0].contains(retry)).toBe(true);
  });

  it('does not render the abnormal-status pill alongside the error region', () => {
    const { container } = render(
      <TurnList parts={failedParts} appId="inside-sales" sessionId={null} streaming={false} onRetry={() => {}} />,
    );
    // the old standalone status pill in the action bar is gone; only the single
    // error region remains.
    const retryButtons = screen.getAllByRole('button', { name: /retry/i });
    expect(retryButtons.length).toBe(1);
    expect(container.querySelectorAll('[data-part-type="error"]').length).toBe(1);
  });
});

const runningSubtask: SubtaskPart = {
  ...BASE,
  id: 'sub-1',
  seq: 2,
  type: 'subtask',
  specialist: 'data_specialist',
  call_id: 'call-1',
  brief: {
    question: 'summarize the latest run',
    scope: { tenant_id: 't', app_id: 'inside-sales', user_id: 'u' },
  },
  state: { status: 'running', started_at: 1 },
};

describe('TurnList live-turn ordering + single shimmer', () => {
  it('renders the pending user bubble BEFORE the thinking glass on a fresh send', () => {
    const { container } = render(
      <TurnList
        parts={[]}
        appId="inside-sales"
        sessionId={null}
        streaming
        pendingUserText="how many leads?"
        onRetry={() => {}}
      />,
    );
    const bubble = screen.getByText('how many leads?');
    const glass = container.querySelector('[data-testid="sherlock-thinking"]');
    expect(bubble).toBeTruthy();
    expect(glass).toBeTruthy();
    // bubble must precede the glass in document order
    expect(
      bubble.compareDocumentPosition(glass as Node) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('does not double the bubble once the server echo lands (reconcile by user-${turnId})', () => {
    // the echo carries id `user-${client_turn_id}` (== pendingTurnId)
    const echo: UserMessagePart = { ...BASE, id: 'user-turn-9', seq: 1, type: 'user_message', text: 'how many leads?' };
    render(
      <TurnList
        parts={[stepStart, echo]}
        appId="inside-sales"
        sessionId={null}
        streaming
        pendingTurnId="turn-9"
        pendingUserText="how many leads?"
        onRetry={() => {}}
      />,
    );
    expect(screen.getAllByText('how many leads?').length).toBe(1);
  });

  it('shows the pending bubble on identical-text retry (id reconcile, not text)', () => {
    // prior turn has a user_message with the SAME text but a DIFFERENT turn id;
    // the new send's echo id (user-turn-2) is not present yet => bubble shows
    const priorStart: StepStartPart = { ...BASE, id: 'ss0', seq: 0, type: 'step_start', turn_id: 'turn-1' };
    const priorUser: UserMessagePart = { ...BASE, id: 'user-turn-1', seq: 1, type: 'user_message', text: 'retry me' };
    render(
      <TurnList
        parts={[priorStart, priorUser]}
        appId="inside-sales"
        sessionId={null}
        streaming
        pendingTurnId="turn-2"
        pendingUserText="retry me"
        onRetry={() => {}}
      />,
    );
    // prior bubble (user-turn-1) + the new optimistic one (user-turn-2 not echoed yet)
    expect(screen.getAllByTestId('user-bubble').length).toBe(2);
  });

  it('does not render a pending bubble for whitespace-only text', () => {
    render(
      <TurnList
        parts={[]}
        appId="inside-sales"
        sessionId={null}
        streaming
        pendingUserText="   "
        onRetry={() => {}}
      />,
    );
    expect(screen.queryAllByTestId('user-bubble').length).toBe(0);
  });

  it('suppresses the standalone thinking glass while a specialist is consulting', () => {
    const { container } = render(
      <TurnList
        parts={[stepStart, userMsg, runningSubtask]}
        appId="inside-sales"
        sessionId={null}
        streaming
        onRetry={() => {}}
      />,
    );
    // the specialist group narrates; no separate glass line
    expect(container.querySelector('[data-testid="sherlock-thinking"]')).toBeNull();
  });

  it('shimmers exactly one line (the active consulting row) while a specialist runs', () => {
    const { container } = render(
      <TurnList
        parts={[stepStart, userMsg, runningSubtask]}
        appId="inside-sales"
        sessionId={null}
        streaming
        onRetry={() => {}}
      />,
    );
    expect(container.querySelectorAll(SHIMMER_SELECTOR).length).toBe(1);
  });
});
