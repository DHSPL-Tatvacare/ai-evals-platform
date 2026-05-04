import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockNavigate = vi.fn();

vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}));

vi.mock('@/services/api/orchestration', () => ({
  createDraftVersion: vi.fn(),
  fireManualRun: vi.fn(),
  getWorkflow: vi.fn(),
  publishVersion: vi.fn(),
}));

vi.mock('@/services/notifications', () => ({
  notificationService: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

import { fireManualRun } from '@/services/api/orchestration';
import { useAppStore } from '@/stores/appStore';
import { WorkflowHeaderBar } from '@/features/orchestration/components/WorkflowHeaderBar';
import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';

describe('WorkflowHeaderBar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAppStore.setState({ currentApp: 'inside-sales' });
    useWorkflowBuilderStore.getState().reset();
    useWorkflowBuilderStore.getState().setMetadata({
      workflowId: 'wf-1',
      versionId: 'ver-1',
      name: 'Concierge Workflow',
      workflowType: 'crm',
      currentPublishedVersionId: 'ver-1',
    });
    (fireManualRun as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 'run-live-1',
    });
  });

  it('navigates to the live run canvas after starting a manual run', async () => {
    render(<WorkflowHeaderBar />);

    fireEvent.click(screen.getByRole('button', { name: 'Run Now' }));

    await waitFor(() => expect(fireManualRun).toHaveBeenCalledWith('wf-1'));
    expect(mockNavigate).toHaveBeenCalledWith('/inside-sales/orchestration/runs/run-live-1');
  });
});
