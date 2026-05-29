// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/hooks', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, useCurrentAppId: () => 'inside-sales' };
});

vi.mock('./queries', () => ({
  useOrchestrationRunReport: vi.fn(),
}));

vi.mock('@/services/api/orchestrationAnalytics', () => ({
  exportRunPdf: vi.fn(),
}));

vi.mock('@/services/notifications', () => ({
  notificationService: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/features/analytics/components/ChartRenderer', () => ({
  ChartRenderer: () => <div data-testid="chart" />,
}));

import { useOrchestrationRunReport } from './queries';
import { exportRunPdf } from '@/services/api/orchestrationAnalytics';
import { notificationService } from '@/services/notifications';
import { RunDrillOver } from './RunDrillOver';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

function seedReport() {
  asMock(useOrchestrationRunReport).mockReturnValue({
    data: {
      runId: 'run-1',
      workflowId: 'wf-1',
      workflowName: 'Welcome blast',
      appId: 'inside-sales',
      status: 'completed',
      triggeredBy: 'manual',
      startedAt: '2026-05-20T10:00:00Z',
      completedAt: '2026-05-20T11:00:00Z',
      durationSeconds: 3600,
      recipientsTotal: 100,
      spend: 1.25,
      buckets: { positive: 20, reached: 40, noResponse: 10, failed: 5, inFlight: 0 },
      channels: [
        {
          capability: 'voice',
          vendor: 'bolna',
          connectionLabel: 'Bolna prod',
          stages: [{ key: 'dialed', label: 'Dialed', count: 100 }],
          metrics: {},
        },
      ],
      recipients: [],
      recipientsTotalCount: 0,
    },
    isLoading: false,
  });
}

function renderOverlay() {
  return render(
    <MemoryRouter>
      <RunDrillOver runId="run-1" appId="inside-sales" scope="tenant" onClose={vi.fn()} />
    </MemoryRouter>,
  );
}

describe('RunDrillOver', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    seedReport();
  });

  it('renders the report view, not the legacy node-path / action-log sections', () => {
    renderOverlay();
    expect(screen.getAllByText('Welcome blast').length).toBeGreaterThan(0);
    expect(screen.queryByText('Node path')).toBeNull();
    expect(screen.queryByText('Action log')).toBeNull();
    // CampaignRunReportView sections render.
    expect(screen.getByText('Outcome mix')).toBeInTheDocument();
  });

  it('shows Export PDF and Open full run actions', () => {
    renderOverlay();
    expect(screen.getByRole('button', { name: /export pdf/i })).toBeInTheDocument();
    expect(screen.getByText(/open full run/i)).toBeInTheDocument();
  });

  it('downloads the PDF and notifies on Export PDF click', async () => {
    asMock(exportRunPdf).mockResolvedValue(new Blob(['pdf'], { type: 'application/pdf' }));
    const createObjectURL = vi.fn(() => 'blob:fake');
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, writable: true });
    Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, writable: true });

    renderOverlay();
    fireEvent.click(screen.getByRole('button', { name: /export pdf/i }));

    await waitFor(() => {
      expect(exportRunPdf).toHaveBeenCalledWith('run-1', { appId: 'inside-sales', scope: 'tenant' });
    });
    await waitFor(() => {
      expect(notificationService.success).toHaveBeenCalledWith('PDF exported');
    });
    expect(createObjectURL).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalled();
  });
});
