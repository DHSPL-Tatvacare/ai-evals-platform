import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { WaitConditionEditor } from '@/features/orchestration/components/editors/WaitConditionEditor';

describe('WaitConditionEditor', () => {
  it('renders only the duration input in duration mode', () => {
    const onChange = vi.fn();
    render(
      <WaitConditionEditor
        value={{ mode: 'duration', duration_hours: 4 }}
        onChange={onChange}
      />,
    );
    expect(screen.getByPlaceholderText('amount')).toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText('hours before timeout fires'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText('wati.message_replied'),
    ).not.toBeInTheDocument();
  });

  it('renders DateTimeField (button trigger) in until_datetime mode — no raw ISO text input', () => {
    const onChange = vi.fn();
    render(
      <WaitConditionEditor
        value={{
          mode: 'until_datetime',
          until_datetime: '2026-05-01T00:00:00Z',
        }}
        onChange={onChange}
      />,
    );
    // DateTimeField renders a <button> trigger — not a free-text input.
    expect(screen.getByRole('button')).toBeInTheDocument();
    // The old free-text ISO placeholder must be gone.
    expect(
      screen.queryByPlaceholderText('2026-05-01T00:00:00Z'),
    ).not.toBeInTheDocument();
    // No duration field visible.
    expect(screen.queryByPlaceholderText('amount')).not.toBeInTheDocument();
  });

  it('renders event + timeout inputs in event_or_timeout mode', () => {
    const onChange = vi.fn();
    render(
      <WaitConditionEditor
        value={{
          mode: 'event_or_timeout',
          event_name: 'wati.replied',
          correlation: {},
          timeout_hours: 24,
        }}
        onChange={onChange}
      />,
    );
    expect(
      screen.getByPlaceholderText('wati.message_replied'),
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText('hours before timeout fires'),
    ).toBeInTheDocument();
    // No duration input.
    expect(screen.queryByPlaceholderText('amount')).not.toBeInTheDocument();
  });

  it('shows event-mode note and event_name caption in event mode', () => {
    const onChange = vi.fn();
    render(
      <WaitConditionEditor
        value={{ mode: 'event', event_name: '' }}
        onChange={onChange}
      />,
    );
    // Approved event-mode note.
    expect(
      screen.getByText(
        "Today this resumes on a WhatsApp reply; full event matching is coming soon.",
      ),
    ).toBeInTheDocument();
    // Approved event_name caption.
    expect(
      screen.getByText(
        "The event that resumes this step — e.g. a WhatsApp reply or a CRM stage change.",
      ),
    ).toBeInTheDocument();
    // event_name remains a free-text input (no picker).
    expect(
      screen.getByPlaceholderText('wati.message_replied'),
    ).toBeInTheDocument();
  });

  it('shows updated event_match help text in event mode', () => {
    const onChange = vi.fn();
    render(
      <WaitConditionEditor
        value={{ mode: 'event', event_name: '' }}
        onChange={onChange}
      />,
    );
    expect(
      screen.getByText(
        /Optional — only resume when the event's data matches these conditions\./,
      ),
    ).toBeInTheDocument();
  });
});
