import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { WaitConditionEditor } from '@/features/orchestration/components/editors/WaitConditionEditor';
import {
  deriveOutputEdgeLabels,
  deriveWaitBodySummary,
} from '@/features/orchestration/utils/nodeOutputs';
import type { WorkflowDefinitionNode } from '@/features/orchestration/types';

function waitNode(config: Record<string, unknown>): WorkflowDefinitionNode {
  return {
    id: 'w1',
    type: 'logic.wait',
    position: { x: 0, y: 0 },
    data: { label: 'logic.wait' },
    config,
  } as WorkflowDefinitionNode;
}

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
      screen.queryByPlaceholderText('hours before giving up'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText('voice.completed'),
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

  it('renders three mode options — pure event is absent', () => {
    const onChange = vi.fn();

    // duration mode: trigger shows its label; help text confirms the option exists.
    const { unmount: u1 } = render(
      <WaitConditionEditor value={{ mode: 'duration' }} onChange={onChange} />,
    );
    expect(screen.getByText('Wait for a set time')).toBeInTheDocument();
    expect(
      screen.getByText('Pause here, then continue after the time you set.'),
    ).toBeInTheDocument();
    u1();

    // until_datetime mode: trigger shows its label.
    const { unmount: u2 } = render(
      <WaitConditionEditor value={{ mode: 'until_datetime' }} onChange={onChange} />,
    );
    expect(screen.getByText('Wait until a specific date & time')).toBeInTheDocument();
    u2();

    // event_or_timeout mode: trigger shows its label — the new event option IS present.
    render(
      <WaitConditionEditor
        value={{ mode: 'event_or_timeout', event_name: '', timeout_hours: 24 }}
        onChange={onChange}
      />,
    );
    expect(screen.getByText('Wait for an event (with a time limit)')).toBeInTheDocument();
    // The removed pure-event option label must not appear anywhere in the DOM.
    // "Wait for event" (exact) was the old label; "Wait for an event …" does NOT contain it.
    expect(screen.queryByText('Wait for event')).not.toBeInTheDocument();
  });

  it('does not render the "coming soon" caveat in any mode', () => {
    const onChange = vi.fn();
    render(
      <WaitConditionEditor
        value={{ mode: 'event_or_timeout', event_name: '', timeout_hours: 24 }}
        onChange={onChange}
      />,
    );
    expect(
      screen.queryByText(/coming soon/i),
    ).not.toBeInTheDocument();
  });

  it('renders event + correlation + timeout inputs in event_or_timeout mode', () => {
    const onChange = vi.fn();
    render(
      <WaitConditionEditor
        value={{
          mode: 'event_or_timeout',
          event_name: 'voice.completed',
          correlation: { recipient_id_field: 'recipient_id' },
          timeout_hours: 24,
        }}
        onChange={onChange}
      />,
    );
    // Event name is now a dropdown; the stored value renders on the trigger.
    expect(screen.getByText('voice.completed')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('recipient_id')).toBeInTheDocument();
    // Timeout now routes through the shared DurationField (amount + unit).
    expect(screen.getByPlaceholderText('amount')).toBeInTheDocument();
    // The old raw hours input placeholder is gone.
    expect(
      screen.queryByPlaceholderText('hours before giving up'),
    ).not.toBeInTheDocument();
  });

  it('steers legacy pure-event mode to event_or_timeout display — no blank Select', () => {
    const onChange = vi.fn();
    render(
      <WaitConditionEditor
        value={{ mode: 'event', event_name: 'voice.completed' }}
        onChange={onChange}
      />,
    );
    // Event fields still render; the stored event name shows on the dropdown trigger.
    expect(screen.getByText('voice.completed')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('recipient_id')).toBeInTheDocument();
    // Timeout field renders via the shared DurationField (defaulted to 24h -> 1 day).
    expect(screen.getByPlaceholderText('amount')).toBeInTheDocument();
    // The caveat line is gone.
    expect(screen.queryByText(/coming soon/i)).not.toBeInTheDocument();
    // onChange has NOT been called (no silent mutation on open).
    expect(onChange).not.toHaveBeenCalled();
  });

  it('editing the duration field drops a stale until_datetime key', () => {
    const onChange = vi.fn();
    render(
      <WaitConditionEditor
        value={{
          mode: 'duration',
          duration_value: 2,
          duration_unit: 'hours',
          // Stale key left behind by a previous until_datetime selection.
          until_datetime: '',
        }}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByPlaceholderText('amount'), {
      target: { value: '15' },
    });
    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0];
    expect(next.mode).toBe('duration');
    expect(next.duration_value).toBe(15);
    expect('until_datetime' in next).toBe(false);
    expect('event_name' in next).toBe(false);
    expect('timeout_hours' in next).toBe(false);
  });

  it('selecting an event drops stale duration keys', () => {
    const onChange = vi.fn();
    render(
      <WaitConditionEditor
        value={{
          mode: 'event_or_timeout',
          event_name: 'voice',
          correlation: { recipient_id_field: 'recipient_id' },
          timeout_hours: 24,
          duration_value: 2,
        }}
        onChange={onChange}
        eventOptions={[{ eventName: 'voice.completed', provider: 'bolna', sourceNodeId: 'v1' }]}
      />,
    );
    // Open the dropdown (trigger shows the current 'voice') and pick the option.
    fireEvent.click(screen.getByText('voice'));
    fireEvent.click(screen.getByText('voice.completed'));
    const next = onChange.mock.calls.at(-1)?.[0];
    expect(next.event_name).toBe('voice.completed');
    expect('duration_value' in next).toBe(false);
    expect('until_datetime' in next).toBe(false);
  });

  it('derives mode-accurate edge labels and a body summary for the canvas', () => {
    expect(
      deriveOutputEdgeLabels(
        waitNode({ mode: 'duration', duration_value: 15, duration_unit: 'minutes' }),
        undefined,
      ),
    ).toEqual({ wakeup: 'After 15 minutes' });
    expect(
      deriveWaitBodySummary(
        waitNode({ mode: 'duration', duration_value: 15, duration_unit: 'minutes' }),
      ),
    ).toBe('Wait 15 minutes');

    expect(
      deriveOutputEdgeLabels(
        waitNode({ mode: 'until_datetime', until_datetime: '2026-05-01T00:00:00Z' }),
        undefined,
      ),
    ).toEqual({ wakeup: 'Until 2026-05-01 00:00 UTC' });
    expect(
      deriveWaitBodySummary(
        waitNode({ mode: 'until_datetime', until_datetime: '2026-05-01T00:00:00Z' }),
      ),
    ).toBe('Wait until 2026-05-01 00:00 UTC');

    expect(
      deriveOutputEdgeLabels(
        waitNode({ mode: 'event_or_timeout', event_name: 'voice.completed', timeout_hours: 24 }),
        undefined,
      ),
    ).toEqual({ event: 'On voice.completed', timeout: 'Timeout 24h' });
    expect(
      deriveWaitBodySummary(
        waitNode({ mode: 'event_or_timeout', event_name: 'voice.completed', timeout_hours: 24 }),
      ),
    ).toBe('Wait for voice.completed · timeout 24h');

    expect(
      deriveWaitBodySummary(waitNode({ mode: 'event', event_name: 'crm.updated' })),
    ).toBe('Wait for: crm.updated');
  });

  it('emits duration_value with the existing unit via the shared DurationField', () => {
    const onChange = vi.fn();
    render(
      <WaitConditionEditor
        value={{ mode: 'duration', duration_value: 2, duration_unit: 'days' }}
        onChange={onChange}
      />,
    );
    // DurationField shows the unit in its trigger.
    expect(screen.getByText('Days')).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText('amount'), {
      target: { value: '6' },
    });
    const next = onChange.mock.calls[0][0];
    expect(next.mode).toBe('duration');
    expect(next.duration_value).toBe(6);
    expect(next.duration_unit).toBe('days');
  });

  it('emits timeout_hours via the shared DurationField in event_or_timeout mode', () => {
    const onChange = vi.fn();
    render(
      <WaitConditionEditor
        value={{
          mode: 'event_or_timeout',
          event_name: 'voice.completed',
          correlation: { recipient_id_field: 'recipient_id' },
          timeout_hours: 24,
        }}
        onChange={onChange}
      />,
    );
    // 24h decomposes to "1 day"; the shared field shows amount + the Days unit.
    const amount = screen.getByPlaceholderText('amount');
    expect(amount).toHaveValue(1);
    expect(screen.getByText('Days')).toBeInTheDocument();
    // 1 day -> 2 days = 48 hours, stored as the canonical timeout_hours int.
    fireEvent.change(amount, { target: { value: '2' } });
    const next = onChange.mock.calls[0][0];
    expect(next.timeout_hours).toBe(48);
  });

  it('renders a Combobox of eventOptions (no free-text) for the event name', () => {
    const onChange = vi.fn();
    render(
      <WaitConditionEditor
        value={{ mode: 'event_or_timeout', event_name: '', timeout_hours: 24 }}
        onChange={onChange}
        eventOptions={[
          { eventName: 'voice.completed', provider: 'bolna', sourceNodeId: 'v1' },
          { eventName: 'crm.updated', provider: 'lsq', sourceNodeId: 'c1' },
        ]}
      />,
    );
    // No free-text input for the event name when options are supplied.
    expect(screen.queryByPlaceholderText('voice.completed')).not.toBeInTheDocument();
    // The Combobox trigger shows its placeholder; opening it lists the events.
    fireEvent.click(screen.getByText('Select an event'));
    expect(screen.getByText('voice.completed')).toBeInTheDocument();
    expect(screen.getByText('crm.updated')).toBeInTheDocument();
  });

  it('emits the selected eventName when an event option is chosen', () => {
    const onChange = vi.fn();
    render(
      <WaitConditionEditor
        value={{ mode: 'event_or_timeout', event_name: '', timeout_hours: 24 }}
        onChange={onChange}
        eventOptions={[{ eventName: 'voice.completed', provider: 'bolna', sourceNodeId: 'v1' }]}
      />,
    );
    fireEvent.click(screen.getByText('Select an event'));
    fireEvent.click(screen.getByText('voice.completed'));
    const next = onChange.mock.calls.at(-1)?.[0];
    expect(next.event_name).toBe('voice.completed');
  });

  it('shows updated approved copy for event_or_timeout mode', () => {
    const onChange = vi.fn();
    render(
      <WaitConditionEditor
        value={{ mode: 'event_or_timeout', event_name: '', timeout_hours: 12 }}
        onChange={onChange}
      />,
    );
    expect(
      screen.getByText('The event that resumes this step — e.g. a call finishing or a CRM update.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('The event field that identifies the contact (defaults to the contact id).'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Optional — only resume when the event's data matches these conditions\./),
    ).toBeInTheDocument();
    // Updated section label.
    expect(screen.getByText('Only resume if… (optional)')).toBeInTheDocument();
  });
});
