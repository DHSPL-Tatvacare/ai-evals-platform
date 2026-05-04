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

  it('starts a manual run and surfaces it via onRunStarted, staying on the builder', async () => {
    // Phase 13 UX: Run Now keeps the user on the builder canvas. Live node
    // pills + edge highlights render in-place via runOverlayStore. The page
    // host receives the run through ``onRunStarted`` to drive the SSE
    // session; navigation is reserved for the explicit "Open run" action
    // on the run-detail surface, never automatic.
    const onRunStarted = vi.fn();
    render(<WorkflowHeaderBar onRunStarted={onRunStarted} />);

    fireEvent.click(screen.getByRole('button', { name: 'Run Now' }));

    await waitFor(() => expect(fireManualRun).toHaveBeenCalledWith('wf-1'));
    await waitFor(() =>
      expect(onRunStarted).toHaveBeenCalledWith(expect.objectContaining({ id: 'run-live-1' })),
    );
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});
