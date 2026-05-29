// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/hooks', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, useCurrentAppId: () => 'inside-sales' };
});

vi.mock('./queries', () => ({
  useOrchestrationOverview: vi.fn(),
  useOrchestrationBreakdown: vi.fn(),
  useOrchestrationRuns: vi.fn(),
  useOrchestrationTrend: vi.fn(),
  useOrchestrationSignals: vi.fn(),
  useOrchestrationRunDetail: vi.fn(),
}));

vi.mock('@/features/analytics/components/ChartRenderer', () => ({
  ChartRenderer: () => <div data-testid="chart" />,
}));

import {
  useOrchestrationBreakdown,
  useOrchestrationOverview,
  useOrchestrationRunDetail,
  useOrchestrationRuns,
  useOrchestrationSignals,
  useOrchestrationTrend,
} from './queries';
import { OrchestrationAnalyticsPage } from './OrchestrationAnalyticsPage';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

function seedHooks() {
  asMock(useOrchestrationOverview).mockReturnValue({
    data: {
      campaigns: 4,
      runs: 12,
      recipients: 320,
      uniqueContacts: 300,
      positive: 80,
      reached: 160,
      noResponse: 40,
      failed: 40,
      inFlight: 12,
      spend: 5.5,
      inFlightRuns: 2,
    },
    isLoading: false,
    isError: false,
  });
  asMock(useOrchestrationBreakdown).mockReturnValue({
    data: { dimension: 'campaign', rows: [] },
    isLoading: false,
  });
  asMock(useOrchestrationRuns).mockReturnValue({
    data: {
      rows: [
        {
          runId: 'run-1',
          workflowId: 'wf-1',
          workflowName: 'Welcome blast',
          channel: 'voice',
          triggeredBy: 'manual',
          status: 'completed',
          cohortSize: 100,
          reached: 60,
          positive: 20,
          cost: 1.25,
          startedAt: '2026-05-20T10:00:00Z',
        },
      ],
      total: 1,
      page: 1,
      pageSize: 20,
    },
    isLoading: false,
  });
  asMock(useOrchestrationTrend).mockReturnValue({
    data: { points: [] },
    isLoading: false,
  });
  asMock(useOrchestrationSignals).mockReturnValue({
    data: { signals: [], generatedAt: null },
    isLoading: false,
  });
  asMock(useOrchestrationRunDetail).mockReturnValue({
    data: {
      runId: 'run-1',
      workflowId: 'wf-1',
      workflowName: 'Welcome blast',
      status: 'completed',
      triggeredBy: 'manual',
      cohortSize: 100,
      startedAt: '2026-05-20T10:00:00Z',
      completedAt: '2026-05-20T11:00:00Z',
      buckets: { positive: 20, reached: 40, noResponse: 10, failed: 5, inFlight: 0 },
      spend: 1.25,
      nodeSteps: [],
      actions: [],
      actionsTotal: 0,
    },
    isLoading: false,
  });
}

function renderPage(scope?: 'mine' | 'tenant') {
  return render(
    <MemoryRouter initialEntries={['/inside-sales/analytics/orchestration']}>
      <OrchestrationAnalyticsPage scope={scope} />
    </MemoryRouter>,
  );
}

describe('OrchestrationAnalyticsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    seedHooks();
  });

  it('renders KPI values from the overview', () => {
    renderPage();
    expect(screen.getByText('Campaigns')).toBeInTheDocument();
    expect(screen.getAllByText('Recipients').length).toBeGreaterThan(0);
    expect(screen.getByText('Spend')).toBeInTheDocument();
    expect(screen.getByText('Positive %')).toBeInTheDocument();
    // Recipients value 320 renders in the KPI tile (and the funnel) — at least one.
    expect(screen.getAllByText('320').length).toBeGreaterThan(0);
  });

  it('renders no scope toggle when mounted with a fixed tenant scope', () => {
    renderPage('tenant');
    expect(screen.queryByRole('tab', { name: /my campaigns/i })).toBeNull();
    expect(screen.queryByRole('tab', { name: /all campaigns/i })).toBeNull();
  });

  it('opens the run drill-over when a run row is clicked', () => {
    renderPage();
    fireEvent.click(screen.getByText('Welcome blast'));
    expect(screen.getByText(/open full run/i)).toBeInTheDocument();
  });
});
