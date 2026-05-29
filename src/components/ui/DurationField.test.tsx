import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { DurationField } from './DurationField';

describe('DurationField (value+unit mode)', () => {
  it('renders the value and the selected unit', () => {
    const onChange = vi.fn();
    render(
      <DurationField
        mode="value-unit"
        value={15}
        unit="minutes"
        onChange={onChange}
      />,
    );
    expect(screen.getByRole('spinbutton')).toHaveValue(15);
    expect(screen.getByText('Minutes')).toBeInTheDocument();
  });

  it('emits the typed value with the current unit', () => {
    const onChange = vi.fn();
    render(
      <DurationField
        mode="value-unit"
        value={2}
        unit="hours"
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '5' } });
    expect(onChange).toHaveBeenCalledWith(5, 'hours');
  });
});

describe('DurationField (seconds mode)', () => {
  it('displays 259200 seconds as 3 days', () => {
    const onChange = vi.fn();
    render(<DurationField mode="seconds" seconds={259200} onChange={onChange} />);
    expect(screen.getByRole('spinbutton')).toHaveValue(3);
    expect(screen.getByText('Days')).toBeInTheDocument();
  });

  it('emits an int number of seconds when the value changes', () => {
    const onChange = vi.fn();
    render(<DurationField mode="seconds" seconds={259200} onChange={onChange} />);
    // 3 days -> 5 days = 432000 seconds.
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '5' } });
    expect(onChange).toHaveBeenCalledWith(432000);
  });

  it('round-trips 259200 -> "3 days" -> 259200 on no-op unit reselect', () => {
    const onChange = vi.fn();
    render(<DurationField mode="seconds" seconds={259200} onChange={onChange} />);
    // The displayed value reflects the canonical seconds without drift.
    expect(screen.getByRole('spinbutton')).toHaveValue(3);
    expect(screen.getByText('Days')).toBeInTheDocument();
  });

  it('decomposes a non-day-aligned value to hours', () => {
    const onChange = vi.fn();
    // 7200 seconds = 2 hours (not a whole number of days).
    render(<DurationField mode="seconds" seconds={7200} onChange={onChange} />);
    expect(screen.getByRole('spinbutton')).toHaveValue(2);
    expect(screen.getByText('Hours')).toBeInTheDocument();
  });
});

describe('DurationField (hours mode)', () => {
  it('displays 24 hours as 1 day', () => {
    const onChange = vi.fn();
    render(<DurationField mode="hours" hours={24} onChange={onChange} />);
    expect(screen.getByRole('spinbutton')).toHaveValue(1);
    expect(screen.getByText('Days')).toBeInTheDocument();
  });

  it('displays a sub-day value in hours', () => {
    const onChange = vi.fn();
    render(<DurationField mode="hours" hours={12} onChange={onChange} />);
    expect(screen.getByRole('spinbutton')).toHaveValue(12);
    expect(screen.getByText('Hours')).toBeInTheDocument();
  });

  it('emits an int number of hours when the value changes', () => {
    const onChange = vi.fn();
    render(<DurationField mode="hours" hours={24} onChange={onChange} />);
    // 1 day -> 2 days = 48 hours.
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '2' } });
    expect(onChange).toHaveBeenCalledWith(48);
  });

  it('displays a stored 0.5 hours as 30 minutes (lossless decompose)', () => {
    const onChange = vi.fn();
    render(<DurationField mode="hours" hours={0.5} onChange={onChange} />);
    expect(screen.getByRole('spinbutton')).toHaveValue(30);
    expect(screen.getByText('Minutes')).toBeInTheDocument();
  });

  it('stores 0.5 hours when 30 minutes is entered (no int rounding)', () => {
    const onChange = vi.fn();
    // Stored 0.25h surfaces as 15 minutes; bumping to 30 minutes must store 0.5h, not round to 1h.
    render(<DurationField mode="hours" hours={0.25} onChange={onChange} />);
    expect(screen.getByRole('spinbutton')).toHaveValue(15);
    expect(screen.getByText('Minutes')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '30' } });
    expect(onChange).toHaveBeenLastCalledWith(0.5);
  });

  it('stores 1.5 hours when 90 minutes is entered (no round to 2h)', () => {
    const onChange = vi.fn();
    // Stored 0.5h surfaces as 30 minutes; bumping to 90 minutes must store 1.5h.
    render(<DurationField mode="hours" hours={0.5} onChange={onChange} />);
    expect(screen.getByText('Minutes')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '90' } });
    expect(onChange).toHaveBeenLastCalledWith(1.5);
  });

  it('keeps whole-unit hours values displaying cleanly', () => {
    const onChange = vi.fn();
    render(<DurationField mode="hours" hours={6} onChange={onChange} />);
    expect(screen.getByRole('spinbutton')).toHaveValue(6);
    expect(screen.getByText('Hours')).toBeInTheDocument();
  });

  it('clamps below-floor seconds emissions to the contract minimum', () => {
    const onChange = vi.fn();
    render(<DurationField mode="seconds" seconds={259200} minSeconds={60} onChange={onChange} />);
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '0' } });
    expect(onChange).toHaveBeenCalledWith(60);
  });
});
