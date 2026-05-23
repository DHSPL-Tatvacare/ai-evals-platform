// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';

// Mock hooks and queries before importing the page
vi.mock('@/hooks', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    useCurrentAppId: () => 'kaira-bot',
  };
});

vi.mock('@/features/reports/queries/reportsQueries', () => ({
  useReportRuns: vi.fn(),
  useReportRunArtifact: vi.fn(),
  useReportConfigs: vi.fn(),
  invalidateReportRuns: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('@/features/analytics/components/RunReportSurface', () => ({
  RunReportSurface: ({ report }: { report: unknown }) => (
    <div data-testid="run-report-surface">{String((report as Record<string, unknown>)?.schemaVersion)}</div>
  ),
  default: ({ report }: { report: unknown }) => (
    <div data-testid="run-report-surface">{String((report as Record<string, unknown>)?.schemaVersion)}</div>
  ),
}));

vi.mock('@/config/routes', () => ({
  analyticsLibraryForApp: (appId: string) => `/${appId}/analytics`,
  analyticsCrossRunReportForApp: (appId: string) => `/${appId}/analytics/cross-run-report`,
}));

vi.mock('@/services/api/jobPolling', () => ({
  submitAndPollJob: vi.fn(),
}));

vi.mock('@/services/notifications', () => ({
  notificationService: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

vi.mock('@/utils/permissions', () => ({
  usePermission: vi.fn().mockReturnValue(true),
}));

// Stub LegacyLlmConfigCompat so we don't need to mock the full credential stack.
vi.mock('@/components/ui', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    LegacyLlmConfigCompat: ({
      onProviderChange,
      onModelChange,
    }: {
      onProviderChange: (p: string) => void;
      onModelChange: (m: string) => void;
    }) => (
      <button
        data-testid="llm-config-stub"
        onClick={() => {
          onProviderChange('gemini');
          onModelChange('gemini-1.5-pro');
        }}
      >
        Select model
      </button>
    ),
  };
});

// TanStack Query QueryClient mock — just enough for useQueryClient() to work.
vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    useQueryClient: () => ({ invalidateQueries: vi.fn().mockResolvedValue(undefined) }),
  };
});

import { useReportRuns, useReportRunArtifact, useReportConfigs } from '@/features/reports/queries/reportsQueries';
import { submitAndPollJob } from '@/services/api/jobPolling';
import { notificationService } from '@/services/notifications';
import { CrossRunReportPage } from './CrossRunReportPage';
import type { ReportRunSummary, ReportConfigSummary } from '@/types';
import type { PlatformCrossRunPayload } from '@/types/platformReports';
import type { Job } from '@/services/api/jobsApi';

const mockUseReportRuns = vi.mocked(useReportRuns);
const mockUseReportRunArtifact = vi.mocked(useReportRunArtifact);
const mockUseReportConfigs = vi.mocked(useReportConfigs);
const mockSubmitAndPollJob = vi.mocked(submitAndPollJob);
const mockNotificationSuccess = vi.mocked(notificationService.success);
const mockNotificationError = vi.mocked(notificationService.error);

function makeRunSummary(overrides: Partial<ReportRunSummary> = {}): ReportRunSummary {
  return {
    id: 'run-1',
    appId: 'kaira-bot',
    reportId: 'report-1',
    scope: 'cross_run',
    status: 'completed',
    tenantId: 'tenant-1',
    userId: 'user-1',
    createdAt: '2026-05-01T00:00:00Z',
    updatedAt: '2026-05-01T00:00:00Z',
    ...overrides,
  };
}

function makeConfigSummary(overrides: Partial<ReportConfigSummary> = {}): ReportConfigSummary {
  return {
    id: 'cfg-1',
    reportId: 'cross-run-v1',
    name: 'Cross-Run Report',
    description: '',
    status: 'active',
    isDefault: true,
    scope: 'cross_run',
    appId: 'kaira-bot',
    tenantId: 'tenant-1',
    userId: 'user-1',
    visibility: 'private',
    presentationConfig: {},
    narrativeConfig: {},
    exportConfig: {},
    defaultReportRunVisibility: 'private',
    version: 1,
    createdAt: '2026-05-01T00:00:00Z',
    updatedAt: '2026-05-01T00:00:00Z',
    ...overrides,
  };
}

function makeCrossRunArtifact(): PlatformCrossRunPayload {
  return {
    schemaVersion: 'v1',
    metadata: {
      appId: 'kaira-bot',
      reportKind: 'cross_run',
      computedAt: '2026-05-01T00:00:00Z',
      sourceRunCount: 3,
      totalRunsAvailable: 3,
      cacheKey: null,
    },
    presentation: {
      sections: [],
      rendererId: 'cross-run-v1',
      layoutGroups: [],
      density: 'comfortable',
      designTokens: {},
      themeTokens: {},
    },
    sections: [],
  };
}

function makeCompletedJob(overrides: Partial<Job> = {}): Job {
  return {
    id: 'job-1',
    jobType: 'generate-cross-run-report',
    status: 'completed',
    params: {},
    result: { report_run_id: 'new-run-1' },
    errorMessage: null,
    createdAt: '2026-05-01T00:00:00Z',
    updatedAt: '2026-05-01T00:00:00Z',
    ...overrides,
  } as Job;
}

function stubQueriesEmpty() {
  mockUseReportRuns.mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    isFetching: false,
  } as unknown as ReturnType<typeof useReportRuns>);

  mockUseReportRunArtifact.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    isFetching: false,
  } as unknown as ReturnType<typeof useReportRunArtifact>);

  mockUseReportConfigs.mockReturnValue({
    data: [makeConfigSummary()],
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof useReportConfigs>);
}

function renderPage() {
  return render(
    <MemoryRouter>
      <CrossRunReportPage />
    </MemoryRouter>,
  );
}

describe('CrossRunReportPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the generate zero-state when no cross-run runs exist', () => {
    stubQueriesEmpty();

    renderPage();

    expect(screen.getByRole('button', { name: /generate report/i })).toBeInTheDocument();
  });

  it('renders RunReportSurface when a completed run and artifact are returned', () => {
    mockUseReportRuns.mockReturnValue({
      data: [makeRunSummary()],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isFetching: false,
    } as unknown as ReturnType<typeof useReportRuns>);

    mockUseReportRunArtifact.mockReturnValue({
      data: makeCrossRunArtifact(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isFetching: false,
    } as unknown as ReturnType<typeof useReportRunArtifact>);

    mockUseReportConfigs.mockReturnValue({
      data: [makeConfigSummary()],
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useReportConfigs>);

    renderPage();

    expect(screen.getByTestId('run-report-surface')).toBeInTheDocument();
  });

  it('opens the generate overlay when "Generate report" is clicked in the empty state', async () => {
    stubQueriesEmpty();
    const user = userEvent.setup();
    renderPage();

    const btn = screen.getByRole('button', { name: /generate report/i });
    await user.click(btn);

    // Overlay should now be visible (title rendered in the slide-over)
    expect(screen.getByText(/generate cross-run report/i)).toBeInTheDocument();
  });

  it('calls submitAndPollJob with correct params when Generate is confirmed', async () => {
    stubQueriesEmpty();
    mockSubmitAndPollJob.mockResolvedValue(makeCompletedJob());

    const user = userEvent.setup();
    renderPage();

    // Open the overlay
    await user.click(screen.getByRole('button', { name: /generate report/i }));

    // Trigger model selection via the stubbed LegacyLlmConfigCompat
    await user.click(screen.getByTestId('llm-config-stub'));

    // Confirm generation
    await user.click(screen.getByRole('button', { name: /^generate$/i }));

    await waitFor(() => {
      expect(mockSubmitAndPollJob).toHaveBeenCalledWith(
        'generate-cross-run-report',
        expect.objectContaining({
          app_id: 'kaira-bot',
          report_id: 'cross-run-v1',
        }),
        expect.objectContaining({ pollIntervalMs: 2000 }),
      );
    });
  });

  it('shows success notification after a successful generation', async () => {
    stubQueriesEmpty();
    mockSubmitAndPollJob.mockResolvedValue(makeCompletedJob());

    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: /generate report/i }));
    await user.click(screen.getByTestId('llm-config-stub'));
    await user.click(screen.getByRole('button', { name: /^generate$/i }));

    await waitFor(() => {
      expect(mockNotificationSuccess).toHaveBeenCalled();
    });
  });

  it('surfaces the job errorMessage when the job fails with "No completed runs" message', async () => {
    stubQueriesEmpty();
    const errorMsg = 'No completed runs with generated reports found.';
    mockSubmitAndPollJob.mockResolvedValue(
      makeCompletedJob({ status: 'failed', errorMessage: errorMsg }),
    );

    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: /generate report/i }));
    await user.click(screen.getByTestId('llm-config-stub'));
    await user.click(screen.getByRole('button', { name: /^generate$/i }));

    await waitFor(() => {
      expect(mockNotificationError).toHaveBeenCalledWith(errorMsg);
    });

    // Error message must also appear in the UI, not be swallowed
    expect(screen.getByText(errorMsg)).toBeInTheDocument();
  });

  it('does not load an artifact or show a hard error when the only run failed', () => {
    mockUseReportRuns.mockReturnValue({
      data: [makeRunSummary({ id: 'failed-run', status: 'failed' })],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isFetching: false,
    } as unknown as ReturnType<typeof useReportRuns>);

    mockUseReportRunArtifact.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isFetching: false,
    } as unknown as ReturnType<typeof useReportRunArtifact>);

    mockUseReportConfigs.mockReturnValue({
      data: [makeConfigSummary()],
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useReportConfigs>);

    renderPage();

    // The failed run must NOT be fetched for an artifact (that 404s -> hard error).
    expect(mockUseReportRunArtifact).toHaveBeenCalledWith(null);
    // No scary "Failed to load report"; instead a retry affordance.
    expect(screen.queryByText('Failed to load report')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /generate report/i })).toBeInTheDocument();
  });

  it('shows the hard load-error only for a completed run whose artifact errors', () => {
    mockUseReportRuns.mockReturnValue({
      data: [makeRunSummary({ status: 'completed' })],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isFetching: false,
    } as unknown as ReturnType<typeof useReportRuns>);

    mockUseReportRunArtifact.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Report artifact not found'),
      refetch: vi.fn(),
      isFetching: false,
    } as unknown as ReturnType<typeof useReportRunArtifact>);

    mockUseReportConfigs.mockReturnValue({
      data: [makeConfigSummary()],
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useReportConfigs>);

    renderPage();

    expect(screen.getByText('Failed to load report')).toBeInTheDocument();
  });

  it('shows Regenerate button in page header when a report already exists', () => {
    mockUseReportRuns.mockReturnValue({
      data: [makeRunSummary()],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isFetching: false,
    } as unknown as ReturnType<typeof useReportRuns>);

    mockUseReportRunArtifact.mockReturnValue({
      data: makeCrossRunArtifact(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isFetching: false,
    } as unknown as ReturnType<typeof useReportRunArtifact>);

    mockUseReportConfigs.mockReturnValue({
      data: [makeConfigSummary()],
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useReportConfigs>);

    renderPage();

    expect(screen.getByRole('button', { name: /regenerate/i })).toBeInTheDocument();
  });
});
