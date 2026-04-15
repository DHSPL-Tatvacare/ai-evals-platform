// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, test, vi } from 'vitest';

import { ChatMessages } from './ChatMessages';
import { useChatWidgetStore } from './useChatWidget';

describe('ChatMessages', () => {
  beforeEach(() => {
    useChatWidgetStore.setState({
      dbSessionId: null,
      sessions: [],
      streamingParts: [],
    });
  });

  test('renders assistant messages from parts and keeps repeated same-name tools separate by toolCallId', async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <ChatMessages
          messages={[
            {
              id: 'assistant-1',
              role: 'assistant',
              status: 'complete',
              parts: [
                {
                  type: 'tool-call',
                  toolCallId: 'tc_1',
                  toolName: 'data_query',
                  state: 'completed',
                  summary: '7 rows',
                  durationMs: 12,
                },
                {
                  type: 'tool-call',
                  toolCallId: 'tc_2',
                  toolName: 'data_query',
                  state: 'completed',
                  summary: '2 rows',
                  durationMs: 18,
                },
                {
                  type: 'text',
                  content: 'Found **9** rows worth reviewing.',
                },
                {
                  type: 'save-toast',
                  variant: 'chart',
                  title: 'Chart saved',
                  subtitle: 'Weekly pass rate',
                  linkText: 'View',
                  linkHref: '/kaira/analytics/charts/chart-1',
                },
              ],
            },
          ]}
          status="idle"
          appId="kaira-bot"
          onRetry={() => {}}
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole('button', { name: /used 2 tools/i })).toBeInTheDocument();
    expect(
      screen.getAllByText((_, element) => element?.textContent === 'Found 9 rows worth reviewing.').length,
    ).toBeGreaterThan(0);
    expect(screen.getByRole('link', { name: /view/i })).toHaveAttribute('href', '/kaira/analytics/charts/chart-1');

    await user.click(screen.getByRole('button', { name: /used 2 tools/i }));

    expect(screen.getAllByText('data_query')).toHaveLength(2);
    expect(screen.getByText('7 rows')).toBeInTheDocument();
    expect(screen.getByText('2 rows')).toBeInTheDocument();
  });

  test('renders retry affordance for terminal error messages', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();

    render(
      <MemoryRouter>
        <ChatMessages
          messages={[
            {
              id: 'assistant-error',
              role: 'assistant',
              status: 'error',
              terminalStatus: 'interrupted',
              parts: [
                {
                  type: 'text',
                  content: 'The stream was interrupted before Sherlock finished.',
                },
              ],
            },
          ]}
          status="error"
          appId="kaira-bot"
          onRetry={onRetry}
        />
      </MemoryRouter>,
    );

    await user.click(screen.getByRole('button', { name: /retry/i }));

    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(screen.getAllByText(/interrupted/i).length).toBeGreaterThan(0);
  });
});
