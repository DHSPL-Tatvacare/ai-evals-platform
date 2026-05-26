// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { render } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const navigate = vi.fn();
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }));

// Run the poll callback exactly once, synchronously, when enabled.
vi.mock('@/hooks', () => ({
  usePoll: ({ fn, enabled }: { fn: () => Promise<boolean>; enabled: boolean }) => {
    if (enabled) void fn();
  },
}));

const notify = vi.fn();
vi.mock('@/services/notifications', () => ({
  notificationService: {
    notify: (...a: unknown[]) => notify(...a),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

const getJob = vi.fn();
vi.mock('@/services/api/jobsApi', () => ({ jobsApi: { get: (id: string) => getJob(id) } }));

// Cross-run job: no runId, so isRunDetailPath is irrelevant; viewPath drives everything.
vi.mock('@/config/routes', () => ({
  isRunDetailPath: () => false,
  runDetailForApp: (appId: string, runId: string) => `/${appId}/runs/${runId}`,
}));

let activeJobs: Array<Record<string, unknown>> = [];
const untrackJob = vi.fn();
const resolveRunId = vi.fn();
vi.mock('@/stores', () => ({
  useJobTrackerStore: Object.assign(
    (selector: (s: unknown) => unknown) => selector({ activeJobs }),
    { getState: () => ({ activeJobs, untrackJob, resolveRunId }) },
  ),
}));

import { JobCompletionWatcher } from './JobCompletionWatcher';

function setPath(pathname: string) {
  window.history.pushState({}, '', pathname);
}

describe('JobCompletionWatcher viewPath routing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    activeJobs = [
      { jobId: 'j1', appId: 'kaira-bot', jobType: 'generate-cross-run-report',
        label: 'Cross-run report', trackedAt: 0,
        viewPath: '/kaira-bot/analytics/cross-run-report' },
    ];
  });

  it('fires a completion toast whose action navigates to viewPath when off-target', async () => {
    setPath('/somewhere-else');
    getJob.mockResolvedValue({ status: 'completed', progress: {}, errorMessage: null });

    render(<JobCompletionWatcher />);
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(notify).toHaveBeenCalledTimes(1);
    const arg = notify.mock.calls[0][0] as { action?: { onClick: () => void } };
    arg.action?.onClick();
    expect(navigate).toHaveBeenCalledWith('/kaira-bot/analytics/cross-run-report');
    expect(untrackJob).toHaveBeenCalledWith('j1');
  });

  it('suppresses the toast when already on the viewPath, but still untracks', async () => {
    setPath('/kaira-bot/analytics/cross-run-report');
    getJob.mockResolvedValue({ status: 'completed', progress: {}, errorMessage: null });

    render(<JobCompletionWatcher />);
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(notify).not.toHaveBeenCalled();
    expect(untrackJob).toHaveBeenCalledWith('j1');
  });
});
