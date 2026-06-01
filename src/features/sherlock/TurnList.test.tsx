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
