import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { DateRangeField } from './DateRangeField';

describe('DateRangeField', () => {
  it('emits a YYYY-MM-DD string when a day is picked (the wire contract)', () => {
    const onFromChange = vi.fn();
    const onToChange = vi.fn();
    render(
      <DateRangeField from="" to="" onFromChange={onFromChange} onToChange={onToChange} />,
    );

    fireEvent.click(screen.getByRole('button', { name: /From/ }));
    fireEvent.click(screen.getByText('15'));

    expect(onFromChange).toHaveBeenCalledTimes(1);
    expect(onFromChange.mock.calls[0][0]).toMatch(/^\d{4}-\d{2}-15$/);
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
});
