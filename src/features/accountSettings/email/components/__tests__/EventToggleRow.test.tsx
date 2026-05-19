import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { EventToggleRow } from '../EventToggleRow';
import type { NotificationSubscriptionRow } from '../../types';

function makeRow(overrides: Partial<NotificationSubscriptionRow> = {}): NotificationSubscriptionRow {
  return {
    eventType: 'scheduled_job.failed',
    group: 'scheduled_job',
    isActive: false,
    isRequired: false,
    recipientEmail: 'alice@x.in',
    ...overrides,
  };
}

describe('EventToggleRow', () => {
  it('renders the user-facing label for a known event', () => {
    render(<EventToggleRow row={makeRow()} pending={false} onToggle={() => {}} />);
    expect(
      screen.getByText(/Email me when a scheduled job I own fails/i),
    ).toBeInTheDocument();
  });

  it('renders the required pill when is_required is true', () => {
    render(
      <EventToggleRow row={makeRow({ isRequired: true })} pending={false} onToggle={() => {}} />,
    );
    expect(screen.getByText(/Required by admin/i)).toBeInTheDocument();
  });

  it('disables the switch when is_required is true', () => {
    render(
      <EventToggleRow row={makeRow({ isRequired: true })} pending={false} onToggle={() => {}} />,
    );
    const sw = screen.getByRole('switch');
    expect(sw).toBeDisabled();
  });

  it('disables the switch while the mutation is pending', () => {
    render(<EventToggleRow row={makeRow()} pending={true} onToggle={() => {}} />);
    expect(screen.getByRole('switch')).toBeDisabled();
  });

  it('fires onToggle when the switch is clicked', () => {
    const onToggle = vi.fn();
    render(<EventToggleRow row={makeRow()} pending={false} onToggle={onToggle} />);
    fireEvent.click(screen.getByRole('switch'));
    expect(onToggle).toHaveBeenCalledWith(true);
  });
});
