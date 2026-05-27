import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { DateRangePicker, type DateRangePreset } from './DateRangePicker';

const PRESETS: DateRangePreset[] = [
  { id: '7d', label: 'Last 7 days' },
  { id: '30d', label: 'Last 30 days' },
  { id: '24h', label: 'Last 24 hours' },
];

describe('DateRangePicker', () => {
  it('shows the active preset label on the trigger', () => {
    render(
      <DateRangePicker
        presets={PRESETS}
        activePreset="7d"
        from={null}
        to={null}
        onPresetSelect={vi.fn()}
        onCustomRange={vi.fn()}
      />,
    );
    expect(screen.getByText('Last 7 days')).toBeInTheDocument();
  });

  it('shows a formatted from–to range when a custom range is active', () => {
    render(
      <DateRangePicker
        presets={PRESETS}
        activePreset={null}
        from="2026-05-01"
        to="2026-05-15"
        onPresetSelect={vi.fn()}
        onCustomRange={vi.fn()}
      />,
    );
    // triggerLabel → `${format(fromDate, 'd MMM')} – ${format(toDateValue, 'd MMM yyyy')}`
    expect(screen.getByText('1 May – 15 May 2026')).toBeInTheDocument();
  });

  it('shows fallback "Date range" when neither preset nor range is set', () => {
    render(
      <DateRangePicker
        presets={PRESETS}
        activePreset={null}
        from={null}
        to={null}
        onPresetSelect={vi.fn()}
        onCustomRange={vi.fn()}
      />,
    );
    expect(screen.getByText('Date range')).toBeInTheDocument();
  });

  it('clicking a preset chip calls onPresetSelect(id) and preset labels are visible', () => {
    const onPresetSelect = vi.fn();
    render(
      <DateRangePicker
        presets={PRESETS}
        activePreset={null}
        from={null}
        to={null}
        onPresetSelect={onPresetSelect}
        onCustomRange={vi.fn()}
      />,
    );

    // Open the popover by clicking the trigger button.
    const trigger = screen.getAllByRole('button')[0];
    fireEvent.click(trigger);

    // Preset chips are now visible inside the popover.
    const chip30d = screen.getByRole('button', { name: 'Last 30 days' });
    expect(chip30d).toBeInTheDocument();
    fireEvent.click(chip30d);

    expect(onPresetSelect).toHaveBeenCalledOnce();
    expect(onPresetSelect).toHaveBeenCalledWith('30d');
  });

  it('clicking a preset chip closes the popover', () => {
    const onPresetSelect = vi.fn();
    render(
      <DateRangePicker
        presets={PRESETS}
        activePreset={null}
        from={null}
        to={null}
        onPresetSelect={onPresetSelect}
        onCustomRange={vi.fn()}
      />,
    );

    const trigger = screen.getAllByRole('button')[0];
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole('button', { name: 'Last 7 days' }));

    // After closing, the preset chips are gone.
    expect(screen.queryByRole('button', { name: 'Last 30 days' })).toBeNull();
  });

  it('onCustomRange is called with ascending dates regardless of click order', () => {
    // jsdom does not lay out elements, so all day buttons in the grid are
    // rendered with the same disabled=false state.  We click two day cells
    // in the calendar: a later date first, then an earlier date.  The
    // component swaps them so onCustomRange always receives (min, max).
    //
    // Strategy: open the popover with from/to seeded to a known past month so
    // the days in the grid are not disabled (they are in the past relative to
    // today = 2026-05-27).  May 2026 has days 1–31; we click day "20" then
    // day "5".  The component will resolve them to 2026-05-05 and 2026-05-20.
    const onCustomRange = vi.fn();
    render(
      <DateRangePicker
        presets={PRESETS}
        activePreset={null}
        from="2026-05-01"
        to="2026-05-01"
        onPresetSelect={vi.fn()}
        onCustomRange={onCustomRange}
      />,
    );

    // Open the popover — trigger is the first button.
    fireEvent.click(screen.getAllByRole('button')[0]);

    // The calendar renders two months side by side (current view + next month).
    // With from="2026-05-01", viewMonth seeds to May 2026.
    // Day buttons are labelled by their day-of-month digit.
    // There may be multiple "20" buttons (one per month panel).
    // We grab all matching buttons and click the first enabled one.
    const allDay20 = screen.getAllByRole('button', { name: '20' });
    const enabledDay20 = allDay20.find((b) => !(b as HTMLButtonElement).disabled);
    expect(enabledDay20).toBeDefined();
    // First click → sets draft.start, clears draft.end.
    fireEvent.click(enabledDay20!);

    // Second click on day "5" → the component swaps if necessary.
    const allDay5 = screen.getAllByRole('button', { name: '5' });
    const enabledDay5 = allDay5.find((b) => !(b as HTMLButtonElement).disabled);
    expect(enabledDay5).toBeDefined();
    fireEvent.click(enabledDay5!);

    expect(onCustomRange).toHaveBeenCalledOnce();
    const [argFrom, argTo] = onCustomRange.mock.calls[0] as [string, string];
    // Ascending order invariant: from ≤ to.
    expect(argFrom <= argTo).toBe(true);
    // Both should be YYYY-MM-DD strings.
    expect(argFrom).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(argTo).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
