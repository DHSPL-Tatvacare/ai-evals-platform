import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockNavigate = vi.fn();

vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}));

vi.mock('@/services/api/orchestration', () => ({
  listWorkflows: vi.fn(),
  listSystemWorkflows: vi.fn(),
  cloneSystemWorkflow: vi.fn(),
}));

vi.mock('@/services/notifications', () => ({
  notificationService: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

vi.mock('@/config/pageMetadata', async () => {
  const actual = await vi.importActual<typeof import('@/config/pageMetadata')>(
    '@/config/pageMetadata',
  );
  return {
    ...actual,
    usePageMetadata: () => ({
      icon: actual.PAGE_METADATA.campaigns.icon,
      title: 'Campaigns',
    }),
  };
});

import {
  cloneSystemWorkflow,
  listSystemWorkflows,
  listWorkflows,
} from '@/services/api/orchestration';
import { WorkflowListPage } from '@/features/orchestration/components/WorkflowListPage';

const tenantWorkflow = {
  id: 'wf-tenant',
  tenantId: 'tenant-1',
  appId: 'inside-sales',
  workflowType: 'crm' as const,
  slug: 'tenant-campaign',
  name: 'Tenant Campaign',
  description: 'owned',
  currentPublishedVersionId: 'ver-1',
  createdBy: 'user-1',
  createdAt: '2026-04-30T00:00:00Z',
  updatedAt: '2026-04-30T00:00:00Z',
};

const systemWorkflow = {
  id: 'wf-system',
  tenantId: 'system',
  appId: 'inside-sales',
  workflowType: 'clinical' as const,
  slug: 'dm2-adherence-watch',
  name: 'DM2 Adherence Watch',
  description: 'seeded',
  currentPublishedVersionId: 'ver-seed',
  createdBy: 'system-user',
  createdAt: '2026-04-30T00:00:00Z',
  updatedAt: '2026-04-30T00:00:00Z',
};

describe('WorkflowListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (listWorkflows as ReturnType<typeof vi.fn>).mockResolvedValue([tenantWorkflow]);
    (listSystemWorkflows as ReturnType<typeof vi.fn>).mockResolvedValue([systemWorkflow]);
    (cloneSystemWorkflow as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...tenantWorkflow,
      id: 'wf-cloned',
      name: 'DM2 Clone',
      slug: 'dm2-clone',
      workflowType: 'clinical',
    });
  });

  it('renders both tenant and system rows in a single unified table with Source badges', async () => {
    render(<WorkflowListPage />);

    await waitFor(() =>
      expect(listWorkflows).toHaveBeenCalledWith({ appId: 'inside-sales' }),
    );
    expect(listSystemWorkflows).toHaveBeenCalledWith({ appId: 'inside-sales' });

    expect(await screen.findByText('Tenant Campaign')).toBeInTheDocument();
    expect(screen.getByText('DM2 Adherence Watch')).toBeInTheDocument();
    expect(screen.getByText('Custom')).toBeInTheDocument();
    expect(screen.getByText('Platform')).toBeInTheDocument();
    // Old section headers must be gone — single unified table.
    expect(screen.queryByText('Your Workflows')).not.toBeInTheDocument();
    expect(screen.queryByText('System Starters')).not.toBeInTheDocument();
  });

  it('Source filter narrows visible rows without re-fetching', async () => {
    render(<WorkflowListPage />);

    await screen.findByText('Tenant Campaign');

    fireEvent.click(screen.getByText('Custom'));
    expect(screen.getByText('Tenant Campaign')).toBeInTheDocument();
    expect(screen.queryByText('DM2 Adherence Watch')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('Platform'));
    expect(screen.queryByText('Tenant Campaign')).not.toBeInTheDocument();
    expect(screen.getByText('DM2 Adherence Watch')).toBeInTheDocument();

    // Filter is purely client-side; backend is fetched once.
    expect(listWorkflows).toHaveBeenCalledTimes(1);
    expect(listSystemWorkflows).toHaveBeenCalledTimes(1);
  });

  it('opens clone dialog and clones a system workflow', async () => {
    render(<WorkflowListPage />);

    await screen.findByText('Clone for Tenant');
    fireEvent.click(screen.getByText('Clone for Tenant'));

    expect(screen.getByText('Clone System Workflow')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Display Name'), {
      target: { value: 'DM2 Clone' },
    });
    fireEvent.change(screen.getByLabelText('Slug (stable id)'), {
      target: { value: 'dm2-clone' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Clone' }));

    await waitFor(() =>
      expect(cloneSystemWorkflow).toHaveBeenCalledWith({
        sourceWorkflowId: 'wf-system',
        newSlug: 'dm2-clone',
        newName: 'DM2 Clone',
        targetAppId: 'inside-sales',
      }),
    );
    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith('/inside-sales/orchestration/workflows/wf-cloned'),
    );
  });
});
