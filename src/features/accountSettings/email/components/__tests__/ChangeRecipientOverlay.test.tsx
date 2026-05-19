import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ChangeRecipientOverlay } from '../ChangeRecipientOverlay';

describe('ChangeRecipientOverlay', () => {
  it('disables Save when value equals current recipient', () => {
    render(
      <ChangeRecipientOverlay
        isOpen
        currentRecipient="alice@x.in"
        onClose={() => {}}
        onSubmit={vi.fn()}
        submitting={false}
      />,
    );
    const save = screen.getByRole('button', { name: /save address/i });
    expect(save).toBeDisabled();
  });

  it('enables Save once the value changes', () => {
    render(
      <ChangeRecipientOverlay
        isOpen
        currentRecipient="alice@x.in"
        onClose={() => {}}
        onSubmit={vi.fn()}
        submitting={false}
      />,
    );
    fireEvent.change(screen.getByPlaceholderText(/name@workspace/i), {
      target: { value: 'alice+notify@x.in' },
    });
    expect(screen.getByRole('button', { name: /save address/i })).not.toBeDisabled();
  });

  it('shows inline format error on invalid email', () => {
    render(
      <ChangeRecipientOverlay
        isOpen
        currentRecipient="alice@x.in"
        onClose={() => {}}
        onSubmit={vi.fn()}
        submitting={false}
      />,
    );
    fireEvent.change(screen.getByPlaceholderText(/name@workspace/i), {
      target: { value: 'not-an-email' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save address/i }));
    expect(screen.getByText(/valid email/i)).toBeInTheDocument();
  });

  it('calls onSubmit with the trimmed new recipient', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <ChangeRecipientOverlay
        isOpen
        currentRecipient="alice@x.in"
        onClose={() => {}}
        onSubmit={onSubmit}
        submitting={false}
      />,
    );
    fireEvent.change(screen.getByPlaceholderText(/name@workspace/i), {
      target: { value: '  alice+notify@x.in  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save address/i }));
    expect(onSubmit).toHaveBeenCalledWith('alice+notify@x.in');
  });
});
