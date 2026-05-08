import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/services/api/adminApi', () => ({
  adminApi: {
    listInviteUses: vi.fn(),
  },
}));

vi.mock('@/services/notifications', () => ({
  notificationService: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

import { adminApi, type InviteLink, type InviteLinkUse } from '@/services/api/adminApi';
import { InviteUsesPanel } from '@/features/admin/InviteUsesPanel';

const mockedListInviteUses = adminApi.listInviteUses as unknown as ReturnType<typeof vi.fn>;

const FIXTURE_INVITE: InviteLink = {
  id: 'invite-1',
  label: 'Engineering team',
  roleId: 'role-1',
  maxUses: 3,
  usesCount: 2,
  expiresAt: '2099-01-01T00:00:00+00:00',
  status: 'active',
  signupMethod: 'password',
  revokedAt: null,
  revokedBy: null,
  revokedByEmail: null,
  createdAt: '2026-05-01T00:00:00+00:00',
  createdBy: 'user-1',
  createdByEmail: 'admin@example.com',
};

describe('InviteUsesPanel', () => {
  beforeEach(() => {
    mockedListInviteUses.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders nothing when no invite is selected', () => {
    const { container } = render(<InviteUsesPanel invite={null} onClose={() => {}} />);
    expect(container.firstChild).toBeNull();
    expect(mockedListInviteUses).not.toHaveBeenCalled();
  });

  it('fetches and renders redemptions in the order returned by the API', async () => {
    const uses: InviteLinkUse[] = [
      {
        id: 'use-2',
        userId: 'u-2',
        userEmail: 'second@example.com',
        usedAt: '2026-05-03T11:00:00+00:00',
        ipHashPrefix: 'aaaabbbbcccc',
      },
      {
        id: 'use-1',
        userId: 'u-1',
        userEmail: 'first@example.com',
        usedAt: '2026-05-02T10:00:00+00:00',
        ipHashPrefix: 'dddd11112222',
      },
    ];
    mockedListInviteUses.mockResolvedValue(uses);

    render(<InviteUsesPanel invite={FIXTURE_INVITE} onClose={() => {}} />);

    await waitFor(() => {
      expect(mockedListInviteUses).toHaveBeenCalledWith('invite-1');
    });

    const second = await screen.findByText('second@example.com');
    const first = await screen.findByText('first@example.com');

    // Server is the authority on order; the table renders rows in that order.
    expect(second.compareDocumentPosition(first) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // IP signatures render as monospace badges.
    expect(screen.getByText('aaaabbbbcccc')).toBeInTheDocument();
    expect(screen.getByText('dddd11112222')).toBeInTheDocument();
  });

  it('renders an empty state when the invite has zero redemptions', async () => {
    mockedListInviteUses.mockResolvedValue([]);

    render(<InviteUsesPanel invite={FIXTURE_INVITE} onClose={() => {}} />);

    await screen.findByText('No redemptions yet');
  });

  it('shows "account deleted" hint when user_id is null', async () => {
    mockedListInviteUses.mockResolvedValue([
      {
        id: 'use-1',
        userId: null,
        userEmail: 'ghost@example.com',
        usedAt: '2026-05-02T10:00:00+00:00',
        ipHashPrefix: 'a1b2c3d4e5f6',
      },
    ]);

    render(<InviteUsesPanel invite={FIXTURE_INVITE} onClose={() => {}} />);

    await screen.findByText('ghost@example.com');
    expect(screen.getByText('account deleted')).toBeInTheDocument();
  });
});
