import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock the hook — no live network calls per CLAUDE.md test rules.
vi.mock('@/features/orchestration/queries/referenceData', () => ({
  useProviderPhoneNumbers: vi.fn(),
  useWatiTemplates: vi.fn(() => ({ data: null })),
  useBolnaAgents: vi.fn(() => ({ data: null, isFetching: false, error: null, refresh: vi.fn() })),
}));

import { useProviderPhoneNumbers } from '@/features/orchestration/queries/referenceData';
import { ProviderPhoneNumberPicker } from '@/features/admin/integrations/ProviderPhoneNumberPicker';

const mockedHook = useProviderPhoneNumbers as ReturnType<typeof vi.fn>;

const ITEMS = [
  { phoneNumber: '+911234567890', label: 'India Main' },
  { phoneNumber: '+447700900001', label: 'UK Secondary' },
];

function idleState(items = ITEMS) {
  return {
    data: { provider: 'wati', items, error: null },
    isFetching: false,
    error: null,
    refresh: vi.fn(),
  };
}

describe('ProviderPhoneNumberPicker', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a combobox with fetched phone numbers when items exist', async () => {
    mockedHook.mockReturnValue(idleState());
    render(
      <ProviderPhoneNumberPicker
        connectionId="conn-1"
        value=""
        onChange={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Select a phone number/i }));
    expect(await screen.findByText('+911234567890 · India Main')).toBeInTheDocument();
    expect(screen.getByText('+447700900001 · UK Secondary')).toBeInTheDocument();
  });

  it('calls onChange with the phone number when an option is selected', async () => {
    mockedHook.mockReturnValue(idleState());
    const onChange = vi.fn();
    render(
      <ProviderPhoneNumberPicker
        connectionId="conn-1"
        value=""
        onChange={onChange}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Select a phone number/i }));
    fireEvent.click(await screen.findByText('+911234567890 · India Main'));
    expect(onChange).toHaveBeenCalledWith('+911234567890');
  });

  it('keeps an already-saved value selectable even when absent from the live list', async () => {
    mockedHook.mockReturnValue(idleState([{ phoneNumber: '+441234567890', label: 'Other' }]));
    const onChange = vi.fn();
    render(
      <ProviderPhoneNumberPicker
        connectionId="conn-1"
        // Saved value not in ITEMS
        value="+999000000000"
        onChange={onChange}
      />,
    );

    // Trigger should show the saved value as the selected label
    expect(screen.getByRole('button', { name: /\+999000000000/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /\+999000000000/ }));
    // Saved value appears in both the trigger label and the dropdown option row.
    const matches = await screen.findAllByText('+999000000000');
    expect(matches.length).toBeGreaterThanOrEqual(2);
  });

  it('renders a free-text input when no connection is provided', () => {
    mockedHook.mockReturnValue({
      data: null,
      isFetching: false,
      error: null,
      refresh: vi.fn(),
    });
    const onChange = vi.fn();
    render(
      <ProviderPhoneNumberPicker
        connectionId={undefined}
        value=""
        onChange={onChange}
      />,
    );

    const input = screen.getByPlaceholderText(/\+91/i);
    expect(input).toBeInTheDocument();
    fireEvent.change(input, { target: { value: '+911111111111' } });
    expect(onChange).toHaveBeenCalledWith('+911111111111');
  });

  it('renders a free-text input when the live list is empty', () => {
    mockedHook.mockReturnValue({
      data: { provider: 'bolna', items: [], error: null },
      isFetching: false,
      error: null,
      refresh: vi.fn(),
    });
    const onChange = vi.fn();
    render(
      <ProviderPhoneNumberPicker
        connectionId="conn-2"
        value=""
        onChange={onChange}
      />,
    );

    const input = screen.getByPlaceholderText(/\+91/i);
    expect(input).toBeInTheDocument();
    fireEvent.change(input, { target: { value: '+912222222222' } });
    expect(onChange).toHaveBeenCalledWith('+912222222222');
  });

  it('surfaces a soft error message when the provider returns one', () => {
    mockedHook.mockReturnValue({
      data: { provider: 'bolna', items: [], error: 'API key invalid' },
      isFetching: false,
      error: null,
      refresh: vi.fn(),
    });
    render(
      <ProviderPhoneNumberPicker
        connectionId="conn-3"
        value=""
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByText('API key invalid')).toBeInTheDocument();
  });
});
