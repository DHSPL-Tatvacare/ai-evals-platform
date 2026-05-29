// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const setAccessToken = vi.fn();
vi.mock('@/stores/authStore', () => ({
  useAuthStore: { getState: () => ({ setAccessToken }) },
}));

vi.mock('@/services/api/orchestrationAnalytics', () => ({
  fetchRunReport: vi.fn(),
}));

vi.mock('./report/CampaignRunReportView', () => ({
  CampaignRunReportView: ({ printMode }: { printMode?: boolean }) => (
    <div data-testid="campaign-report-view" data-print={String(Boolean(printMode))} />
  ),
}));

import { fetchRunReport } from '@/services/api/orchestrationAnalytics';
import { PrintCampaignRun } from './PrintCampaignRun';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

function renderPrint(search = '?appId=inside-sales&scope=tenant') {
  // The print page reads appId/scope from the real browser location (set by
  // Playwright on navigate), so mirror that into jsdom's location for the test.
  window.history.replaceState(null, '', `/print/campaign-runs/run-1${search}`);
  return render(
    <MemoryRouter initialEntries={[`/print/campaign-runs/run-1${search}`]}>
      <Routes>
        <Route path="/print/campaign-runs/:runId" element={<PrintCampaignRun />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('PrintCampaignRun', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    document.body.removeAttribute('data-report-ready');
    document.body.removeAttribute('data-report-error');
    document.documentElement.removeAttribute('data-theme');
  });

  it('forces light theme on mount', () => {
    asMock(fetchRunReport).mockReturnValue(new Promise(() => {}));
    renderPrint();
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });

  it('renders the report view in print mode and signals readiness', async () => {
    asMock(fetchRunReport).mockResolvedValue({
      runId: 'run-1',
      workflowName: 'Welcome blast',
      channels: [],
      recipients: [],
      buckets: { positive: 0, reached: 0, noResponse: 0, failed: 0, inFlight: 0 },
    });
    renderPrint();

    const view = await screen.findByTestId('campaign-report-view');
    expect(view).toHaveAttribute('data-print', 'true');
    await waitFor(() => {
      expect(document.body.getAttribute('data-report-ready')).toBe('true');
    });
    expect(fetchRunReport).toHaveBeenCalledWith('run-1', { appId: 'inside-sales', scope: 'tenant' });
  });

  it('sets data-report-error when the fetch fails', async () => {
    asMock(fetchRunReport).mockRejectedValue(new Error('boom'));
    renderPrint();
    await waitFor(() => {
      expect(document.body.getAttribute('data-report-error')).toBe('boom');
    });
    expect(document.body.getAttribute('data-report-ready')).toBe('true');
  });
});
