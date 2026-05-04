import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/services/api/orchestration', () => ({
  listRunActions: vi.fn(),
}));

vi.mock('@/features/orchestration/components/ActionDetailPanel', () => ({
  ActionDetailPanel: ({
    action,
    open,
  }: {
    action: { id: string } | null;
    open: boolean;
  }) => (open && action ? <div data-testid="action-detail">{action.id}</div> : null),
}));

import { listRunActions } from '@/services/api/orchestration';
import { ActionLogTab } from '@/features/orchestration/components/ActionLogTab';

const mockedListRunActions = listRunActions as ReturnType<typeof vi.fn>;

describe('ActionLogTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedListRunActions.mockResolvedValue([
      {
        id: 'action-1',
        recipientId: 'lead-1',
        channel: 'bolna',
        actionType: 'bolna_queued',
        status: 'success',
        idempotencyKey: 'idem-1',
        payload: {},
        response: {
          provider_status: 'completed',
          provider_terminal: true,
          hangup_reason: 'caller_hangup',
        },
        error: null,
        parentActionId: null,
        createdAt: '2026-05-04T10:00:00Z',
        completedAt: '2026-05-04T10:01:00Z',
      },
    ]);
  });

  it('renders the detail chip and opens the detail panel on row click', async () => {
    render(<ActionLogTab runId="run-1" runStatus="completed" />);

    await waitFor(() =>
      expect(mockedListRunActions).toHaveBeenCalledWith('run-1', { limit: 100 }),
    );

    expect(await screen.findByText('completed')).toBeInTheDocument();
    fireEvent.click(screen.getByText('lead-1'));
    expect(screen.getByTestId('action-detail')).toHaveTextContent('action-1');
  });
});
