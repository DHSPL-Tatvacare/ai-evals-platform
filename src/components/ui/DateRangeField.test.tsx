import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { DateRangeField } from './DateRangeField';
import { Calendar } from './Calendar';

describe('DateRangeField', () => {
  it('emits a YYYY-MM-DD string when a day is picked (the wire contract)', () => {
    const onFromChange = vi.fn();
    const onToChange = vi.fn();
    render(
      <DateRangeField from="" to="" onFromChange={onFromChange} onToChange={onToChange} />,
    );

    fireEvent.click(screen.getByRole('button', { name: /From/ }));
    // Day 1 of the current month is always selectable (never after today).
    fireEvent.click(screen.getByRole('button', { name: '1' }));

    expect(onFromChange).toHaveBeenCalledTimes(1);
    expect(onFromChange.mock.calls[0][0]).toMatch(/^\d{4}-\d{2}-01$/);
    expect(onToChange).not.toHaveBeenCalled();
  });

  it('shows the formatted date on the trigger when a value is set', () => {
    render(
      <DateRangeField
        from="2026-05-07"
        to=""
        onFromChange={vi.fn()}
        onToChange={vi.fn()}
      />,
    );
    expect(screen.getByText('7 May 2026')).toBeInTheDocument();
  });

  it('does not render or reach days after max (no future shown)', () => {
    const onSelect = vi.fn();
    const mid = new Date(2026, 4, 15);
    render(<Calendar value={mid} max={mid} onSelect={onSelect} />);

    // A day after the 15th is not rendered at all — not greyed, gone.
    expect(screen.queryByRole('button', { name: '20' })).toBeNull();
    // And the future is unreachable: next-month navigation is disabled.
    expect(screen.getByRole('button', { name: /next month/i })).toBeDisabled();
  });
});
