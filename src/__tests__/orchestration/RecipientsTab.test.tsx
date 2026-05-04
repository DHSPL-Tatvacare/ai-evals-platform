import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/services/api/orchestration', () => ({
  listRunRecipients: vi.fn(),
}));

vi.mock('@/features/orchestration/components/OverrideMenu', () => ({
  OverrideMenu: () => <div data-testid="override-menu">override</div>,
}));

import { listRunRecipients } from '@/services/api/orchestration';
import { RecipientsTab } from '@/features/orchestration/components/RecipientsTab';

const mockedListRunRecipients = listRunRecipients as ReturnType<typeof vi.fn>;

describe('RecipientsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedListRunRecipients.mockResolvedValue([
      {
        recipientId: 'lead-1',
        currentNodeId: 'crm.send_wati',
        status: 'waiting',
        wakeupAt: null,
        payload: {
          last_outcome: 'wa_replied',
          last_event_at: '2026-05-04T12:00:00Z',
        },
        enrolledAt: '2026-05-04T10:00:00Z',
        completedAt: null,
        error: null,
      },
    ]);
  });

  it('renders the last outcome and last event columns from recipient payload', async () => {
    render(<RecipientsTab runId="run-1" runStatus="completed" />);

    await waitFor(() =>
      expect(mockedListRunRecipients).toHaveBeenCalledWith('run-1', {
        limit: 50,
        offset: 0,
      }),
    );

    expect(await screen.findByText('wa_replied')).toBeInTheDocument();
    expect(
      screen.getByText(new Date('2026-05-04T12:00:00Z').toLocaleString()),
    ).toBeInTheDocument();
  });
});
