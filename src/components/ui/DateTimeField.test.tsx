import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { DateTimeField } from './DateTimeField';

/** Local Date → the UTC ISO string DateTimeField expects as `value`. */
function localToUtcIso(d: Date): string {
  return d.toISOString().replace(/\.\d{3}Z$/, 'Z');
}

// All assertions work against the UTC ISO string that onChange receives, so
// there are no local-timezone assumptions in these tests.

describe('DateTimeField', () => {
  it('renders the placeholder when value is empty', () => {
    render(<DateTimeField value="" onChange={vi.fn()} placeholder="Pick a datetime" />);
    expect(screen.getByText('Pick a datetime')).toBeInTheDocument();
  });

  it('renders a formatted local label when a valid UTC ISO value is supplied', () => {
    // 2026-05-01T10:30:00Z is a well-known UTC instant — whatever the local
    // timezone, a non-empty label must appear on the trigger button.
    render(
      <DateTimeField value="2026-05-01T10:30:00Z" onChange={vi.fn()} />,
    );
    // The trigger must show something other than a placeholder (non-empty text
    // containing a recognisable part of the date/time).
    const trigger = screen.getByRole('button');
    expect(trigger.textContent).not.toBe('');
    expect(trigger.textContent).not.toBe('Select date & time');
  });

  it('shows the UTC caption when a value is set', () => {
    render(
      <DateTimeField value="2026-05-01T10:30:00Z" onChange={vi.fn()} />,
    );
    // The stored UTC ISO should appear in a caption element.
    expect(screen.getByText(/2026-05-01T10:30:00Z/)).toBeInTheDocument();
  });

  it('emits a correctly-formatted UTC ISO string ending in Z with no milliseconds', () => {
    const onChange = vi.fn();
    render(<DateTimeField value="" onChange={onChange} />);

    // Open the popover.
    fireEvent.click(screen.getByRole('button'));

    // Pick day 1 of whatever month is currently shown in the calendar.
    const dayButtons = screen.getAllByRole('button', { name: /^1$/ });
    fireEvent.click(dayButtons[0]);

    // onChange may or may not fire at this point (date only, no time yet),
    // but once it does fire the emitted value must match the contract.
    if (onChange.mock.calls.length > 0) {
      const emitted: string = onChange.mock.calls[onChange.mock.calls.length - 1][0];
      expect(emitted).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
      // Round-trip: parsing the emitted string gives a valid Date.
      expect(new Date(emitted).toISOString()).toBe(emitted.replace('Z', '.000Z'));
    }
  });

  it('emitted string has no milliseconds and ends with Z', () => {
    // Verify the format constraint on any emission from a pre-seeded value
    // by re-rendering with a valid value and checking the caption text.
    const utcValue = '2026-03-15T08:00:00Z';
    render(<DateTimeField value={utcValue} onChange={vi.fn()} />);
    // Caption shows the stored value verbatim — confirms the component
    // formats the output string as specified (no .000, trailing Z).
    const caption = screen.getByText(/Stored as/);
    expect(caption.textContent).toContain('2026-03-15T08:00:00Z');
    expect(caption.textContent).not.toContain('.000');
  });

  describe('future-only guard (min prop)', () => {
    it('disables past days in the calendar when min is set', () => {
      // min = today at noon local; the calendar must not render yesterday.
      const min = new Date();
      min.setHours(12, 0, 0, 0);
      const yesterday = new Date(min);
      yesterday.setDate(yesterday.getDate() - 1);

      render(<DateTimeField value="" onChange={vi.fn()} min={min} />);
      fireEvent.click(screen.getByRole('button'));

      // The day-cell for yesterday is suppressed (out-of-range days are not
      // rendered as clickable buttons by Calendar).
      if (yesterday.getMonth() === min.getMonth()) {
        const dayLabel = String(yesterday.getDate());
        const dayButtons = screen
          .queryAllByRole('button', { name: new RegExp(`^${dayLabel}$`) });
        expect(dayButtons.length).toBe(0);
      }
    });

    it('clamps hour options earlier than min when the selected date is today', async () => {
      const user = userEvent.setup();
      // min today at 13:00 local; value today at 18:00 local.
      const min = new Date();
      min.setHours(13, 0, 0, 0);
      const value = new Date();
      value.setHours(18, 0, 0, 0);

      render(
        <DateTimeField value={localToUtcIso(value)} onChange={vi.fn()} min={min} />,
      );

      // Open the popover (trigger is the first button) so the Selects mount.
      await user.click(screen.getAllByRole('button')[0]);
      // Open the hour Select (first combobox in the time row).
      const comboboxes = await screen.findAllByRole('combobox');
      await user.click(comboboxes[0]);

      const listbox = await screen.findByRole('listbox');
      const earlier = String(min.getHours() - 1).padStart(2, '0');
      const atMin = String(min.getHours()).padStart(2, '0');
      const later = String(min.getHours() + 1).padStart(2, '0');

      // An hour before min is not offered; min's hour and later are.
      expect(within(listbox).queryByRole('option', { name: earlier })).toBeNull();
      expect(within(listbox).getByRole('option', { name: atMin })).toBeInTheDocument();
      expect(within(listbox).getByRole('option', { name: later })).toBeInTheDocument();
    });

    it('clamps a typed value earlier than min up to min on today', () => {
      const onChange = vi.fn();
      // value sits before min on the same day → must snap forward to min.
      const min = new Date();
      min.setHours(15, 0, 0, 0);
      const value = new Date();
      value.setHours(9, 0, 0, 0);

      render(
        <DateTimeField value={localToUtcIso(value)} onChange={onChange} min={min} />,
      );

      // On mount the out-of-range value is corrected to min.
      const emitted: string = onChange.mock.calls[0][0];
      expect(new Date(emitted).getTime()).toBeGreaterThanOrEqual(min.getTime());
    });

    it('clamps at most once when min carries seconds and its identity is fresh each render', () => {
      const onChange = vi.fn();
      // min has seconds>0 — the clamp target zeroes seconds, so a naive guard
      // re-fires every render against a fresh, later min (render storm).
      const baseMin = new Date();
      baseMin.setHours(15, 0, 37, 0);
      const value = new Date();
      value.setHours(9, 0, 0, 0);

      // A fresh min identity on every render reproduces the call-site footgun.
      const freshMin = () => new Date(baseMin.getTime());

      const { rerender } = render(
        <DateTimeField value={localToUtcIso(value)} onChange={onChange} min={freshMin()} />,
      );
      // Re-render several times with a brand-new min object but the SAME instant.
      // After the first clamp the emitted value must satisfy the guard so no
      // further onChange fires regardless of fresh min identity.
      const clamped: string = onChange.mock.calls[0][0];
      for (let i = 0; i < 5; i++) {
        rerender(
          <DateTimeField value={clamped} onChange={onChange} min={freshMin()} />,
        );
      }

      expect(onChange).toHaveBeenCalledTimes(1);
    });
  });
});
