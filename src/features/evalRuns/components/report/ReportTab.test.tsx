// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('@/features/reports/queries/reportsQueries', () => ({
  useReportConfigs: vi.fn(),
  useReportRuns: vi.fn(),
  useReportRunArtifact: vi.fn(),
  invalidateReportRuns: vi.fn().mockResolvedValue(undefined),
  invalidateReportConfigs: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('@/services/api/jobPolling', () => ({
  submitAndPollJob: vi.fn(),
  pollJobUntilComplete: vi.fn().mockReturnValue(new Promise(() => {})),
}));
vi.mock('@/services/api/aiSettingsQueries', () => ({ useProviderConfigs: () => ({ data: [] }) }));
vi.mock('@/utils/permissions', () => ({ usePermission: () => true }));
vi.mock('@/services/notifications', () => ({
  notificationService: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
vi.mock('@/services/api/jobsApi', () => ({ jobsApi: { get: vi.fn(), cancel: vi.fn() } }));
vi.mock('@/services/api/reportsApi', () => ({ reportsApi: { exportReportRunPdf: vi.fn() } }));
vi.mock('@/features/chat-widget/useChatWidget', () => ({
  useChatWidgetStore: { getState: () => ({ open: false, toggle: vi.fn() }) },
}));
vi.mock('@/features/settings/components/SettingsSlideOver', () => ({ SettingsSlideOver: () => null }));
vi.mock('./ManageBlueprintsSlideOver', () => ({ ManageBlueprintsSlideOver: () => null }));

const trackJob = vi.fn();
const untrackJob = vi.fn();
vi.mock('@/stores', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, useJobTrackerStore: { getState: () => ({ trackJob, untrackJob }) } };
});
vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, useQueryClient: () => ({ invalidateQueries: vi.fn().mockResolvedValue(undefined) }) };
});

import { useReportConfigs, useReportRuns, useReportRunArtifact } from '@/features/reports/queries/reportsQueries';
import ReportTab from './ReportTab';
import type { ReportRunSummary, ReportConfigSummary } from '@/types';

const run = (o: Partial<ReportRunSummary>): ReportRunSummary => ({
  id: 'x', appId: 'kaira-bot', reportId: 'r1', scope: 'single_run', status: 'completed',
  tenantId: 't', userId: 'u', createdAt: '2026-05-01T00:00:00Z', updatedAt: '2026-05-01T00:00:00Z', ...o,
});
const cfg = (o: Partial<ReportConfigSummary> = {}): ReportConfigSummary => ({
  id: 'cfg-1', reportId: 'r1', name: 'Default', description: '', status: 'active', isDefault: true,
  scope: 'single_run', appId: 'kaira-bot', tenantId: 't', userId: 'u', visibility: 'private',
  presentationConfig: {}, narrativeConfig: {}, exportConfig: {}, defaultReportRunVisibility: 'private',
  version: 1, createdAt: '2026-05-01T00:00:00Z', updatedAt: '2026-05-01T00:00:00Z', ...o,
});
const ok = <T,>(data: T) => ({ data, isLoading: false, isError: false, error: null }) as unknown as never;

describe('ReportTab in-flight selection', () => {
  beforeEach(() => vi.clearAllMocks());

  it('selects the running run over a completed one so the resume poll fires after refresh', () => {
    vi.mocked(useReportConfigs).mockReturnValue(ok([cfg()]));
    vi.mocked(useReportRuns).mockReturnValue(ok([
      run({ id: 'running-1', status: 'running', jobId: 'job-1' }),
      run({ id: 'done-1', status: 'completed' }),
    ]));
    vi.mocked(useReportRunArtifact).mockReturnValue(ok(undefined));

    render(<ReportTab appId="kaira-bot" runId="eval-1" renderReport={(_r, a) => <div>{a}</div>} />);

    expect(screen.getByText(/generating report/i)).toBeInTheDocument();
  });
});
