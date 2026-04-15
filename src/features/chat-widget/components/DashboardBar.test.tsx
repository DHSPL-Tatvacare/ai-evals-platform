// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, test, vi } from 'vitest';

import { DashboardBar } from './DashboardBar';
import { analyticsLibraryApi } from '@/services/api/analyticsLibraryApi';

vi.mock('@/services/api/analyticsLibraryApi', () => ({
  analyticsLibraryApi: {
    saveChart: vi.fn(),
    saveDashboard: vi.fn(),
  },
}));

describe('DashboardBar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test('creates a dashboard without requiring router context and emits a save toast payload', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();

    vi.mocked(analyticsLibraryApi.saveChart)
      .mockResolvedValueOnce({ id: 'chart-1' } as never)
      .mockResolvedValueOnce({ id: 'chart-2' } as never);
    vi.mocked(analyticsLibraryApi.saveDashboard).mockResolvedValue({ id: 'dash-1' } as never);

    render(
      <DashboardBar
        appId="kaira-bot"
        sessionId="session-1"
        charts={[
          {
            type: 'chart',
            spec: {
              type: 'bar',
              title: 'Pass rate',
              xKey: 'week',
              yKey: 'value',
              seriesKeys: ['value'],
              xLabel: 'Week',
              yLabel: 'Pass rate',
            },
            data: [{ week: 'W1', value: 90 }],
            sqlQuery: 'select 1',
            sourceQuestion: 'show pass rate',
          },
          {
            type: 'chart',
            spec: {
              type: 'line',
              title: 'Volume',
              xKey: 'week',
              yKey: 'count',
              seriesKeys: ['count'],
              xLabel: 'Week',
              yLabel: 'Count',
            },
            data: [{ week: 'W1', count: 12 }],
            sqlQuery: 'select 2',
            sourceQuestion: 'show volume',
          },
        ]}
        defaultTitle="Weekly dashboard"
        onSaved={onSaved}
      />,
    );

    expect(screen.getByDisplayValue('Weekly dashboard')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /create/i }));

    await waitFor(() => {
      expect(analyticsLibraryApi.saveChart).toHaveBeenCalledTimes(2);
      expect(analyticsLibraryApi.saveDashboard).toHaveBeenCalledWith({
        appId: 'kaira-bot',
        title: 'Weekly dashboard',
        chartIds: ['chart-1', 'chart-2'],
        sourceSessionId: 'session-1',
      });
    });

    expect(onSaved).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'save-toast',
        variant: 'dashboard',
        linkHref: '/kaira/analytics/dashboards/dash-1',
      }),
    );
  });
});
