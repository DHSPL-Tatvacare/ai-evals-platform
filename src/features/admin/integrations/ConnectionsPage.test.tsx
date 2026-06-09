// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import type { Connection } from '@/services/api/orchestrationConnections';

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
}));

vi.mock('@/config/pageMetadata', () => ({
  usePageMetadata: () => ({ icon: () => null, title: 'Connections' }),
}));

vi.mock('@/stores/authStore', () => ({
  useAuthStore: (selector: (s: unknown) => unknown) =>
    selector({ user: { id: 'u1', appAccess: ['inside-sales'] } }),
}));

vi.mock('@/features/orchestration/utils/access', () => ({
  canManageOrchestration: () => true,
  canEditOrchestrationAsset: () => true,
}));

// Render the page form inert; we only assert page chrome + actions.
vi.mock('./ConnectionForm', () => ({ ConnectionForm: () => null }));

const updateMutate = vi.fn();
let rows: Connection[] = [];
vi.mock('./queries', () => ({
  useConnections: () => ({ data: rows, isLoading: false, error: null, refetch: vi.fn() }),
  useTestConnection: () => ({ mutate: vi.fn(), isPending: false, variables: undefined }),
  useRotateToken: () => ({ mutate: vi.fn(), isPending: false, variables: undefined }),
  useUpdateConnection: () => ({ mutate: updateMutate, isPending: false, variables: undefined }),
}));

function comm(overrides: Partial<Connection> = {}): Connection {
  return {
    id: 'c-comm',
    tenantId: 't1',
    appId: 'inside-sales',
    tenantWide: false,
    appScopes: [],
    isDefault: false,
    provider: 'bolna',
    name: 'Voice prod',
    active: true,
    lastUsedAt: null,
    webhookUrl: null,
    configRedacted: {},
    fields: [],
    createdBy: 'u1',
    createdAt: '',
    updatedAt: '',
    ...overrides,
  };
}

function crm(overrides: Partial<Connection> = {}): Connection {
  return { ...comm({ id: 'c-crm', provider: 'lsq', name: 'LSQ prod' }), ...overrides };
}

import { ConnectionsPage } from './ConnectionsPage';

beforeEach(() => {
  updateMutate.mockReset();
  rows = [];
});

describe('ConnectionsPage', () => {
  it('labels each connection with its category in one table', () => {
    rows = [comm(), crm()];
    render(<ConnectionsPage />);
    expect(screen.getByText('Communication')).toBeInTheDocument();
    expect(screen.getByText('Data & CRM')).toBeInTheDocument();
  });

  it('has no visibility filter pills', () => {
    rows = [comm()];
    render(<ConnectionsPage />);
    expect(screen.queryByText('Shared')).not.toBeInTheDocument();
    expect(screen.queryByText('Private')).not.toBeInTheDocument();
    expect(screen.queryByText('Visibility')).not.toBeInTheDocument();
  });

  it('deactivates an active connection through useUpdateConnection after confirm', () => {
    rows = [comm({ active: true })];
    render(<ConnectionsPage />);
    fireEvent.click(screen.getByLabelText('Row actions'));
    fireEvent.click(screen.getByText('Deactivate'));
    // Active -> Inactive is gated by a confirm dialog.
    fireEvent.click(screen.getByRole('button', { name: 'Deactivate' }));
    expect(updateMutate).toHaveBeenCalledWith(
      { id: 'c-comm', body: { active: false } },
      expect.anything(),
    );
  });

  it('activates an inactive connection immediately', () => {
    rows = [comm({ active: false })];
    render(<ConnectionsPage />);
    fireEvent.click(screen.getByLabelText('Row actions'));
    fireEvent.click(screen.getByText('Activate'));
    expect(updateMutate).toHaveBeenCalledWith(
      { id: 'c-comm', body: { active: true } },
      expect.anything(),
    );
  });
});
