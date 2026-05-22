// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

// Mock hooks and queries before importing the page
vi.mock('@/hooks', () => ({
  useCurrentAppId: () => 'kaira-bot',
}));

vi.mock('@/features/reports/queries/reportsQueries', () => ({
  useReportRuns: vi.fn(),
  useReportRunArtifact: vi.fn(),
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

import { useReportRuns, useReportRunArtifact } from '@/features/reports/queries/reportsQueries';
import { CrossRunReportPage } from './CrossRunReportPage';
import type { ReportRunSummary } from '@/types';
import type { PlatformCrossRunPayload } from '@/types/platformReports';

const mockUseReportRuns = vi.mocked(useReportRuns);
const mockUseReportRunArtifact = vi.mocked(useReportRunArtifact);

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

function renderPage() {
  return render(
    <MemoryRouter>
      <CrossRunReportPage />
    </MemoryRouter>,
  );
}

describe('CrossRunReportPage', () => {
  it('shows empty state when no cross-run runs exist', () => {
    // stub both queries — no runs, no artifact
    mockUseReportRuns.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useReportRuns>);

    mockUseReportRunArtifact.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useReportRunArtifact>);

    renderPage();

    expect(screen.getByText('No cross-run report yet')).toBeInTheDocument();
  });

  it('renders RunReportSurface when a completed run and artifact are returned', () => {
    mockUseReportRuns.mockReturnValue({
      data: [makeRunSummary()],
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useReportRuns>);

    mockUseReportRunArtifact.mockReturnValue({
      data: makeCrossRunArtifact(),
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useReportRunArtifact>);

    renderPage();

    expect(screen.getByTestId('run-report-surface')).toBeInTheDocument();
  });
});
