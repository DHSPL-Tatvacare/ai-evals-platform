import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock the hook — no live network calls per CLAUDE.md test rules.
vi.mock('@/features/orchestration/queries/referenceData', () => ({
  useProviderPhoneNumbers: vi.fn(),
  useWatiTemplates: vi.fn(() => ({ data: null })),
  useBolnaAgents: vi.fn(() => ({ data: null, isFetching: false, error: null, refresh: vi.fn() })),
}));

// Mock getConnection for the stored-channel fallback path.
vi.mock('@/services/api/orchestrationConnections', () => ({
  getConnection: vi.fn(),
}));

import { useProviderPhoneNumbers } from '@/features/orchestration/queries/referenceData';
import { getConnection } from '@/services/api/orchestrationConnections';
import { WatiChannelPicker } from '@/features/admin/integrations/WatiChannelPicker';

const mockedHook = useProviderPhoneNumbers as ReturnType<typeof vi.fn>;
const mockedGetConnection = getConnection as ReturnType<typeof vi.fn>;

const LIVE_ITEMS = [
  { phoneNumber: '+911234567890', label: 'Main Channel' },
  { phoneNumber: '+447700900001', label: 'UK Channel' },
];

const STORED_CHANNELS = ['+919876543210', '+441234567890'];

function makeConnection(channelNumbers: string[]) {
  return {
    id: 'conn-wati',
    provider: 'wati',
    configRedacted: { channel_numbers: channelNumbers },
  };
}

describe('WatiChannelPicker', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows prompt when no connection is selected', () => {
    mockedHook.mockReturnValue({ data: null, isFetching: false, error: null, refresh: vi.fn() });
    render(<WatiChannelPicker value="" onChange={vi.fn()} />);
    expect(screen.getByText(/Pick a WATI connection/i)).toBeInTheDocument();
  });

  it('renders live channel numbers from the endpoint when available', async () => {
    mockedHook.mockReturnValue({
      data: { provider: 'wati', items: LIVE_ITEMS, error: null },
      isFetching: false,
      error: null,
      refresh: vi.fn(),
    });

    render(
      <WatiChannelPicker connectionId="conn-wati" value="" onChange={vi.fn()} />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Select a channel number/i }));
    expect(await screen.findByText('+911234567890 · Main Channel')).toBeInTheDocument();
    expect(screen.getByText('+447700900001 · UK Channel')).toBeInTheDocument();
  });

  it('calls onChange with the phone number when an option is selected', async () => {
    mockedHook.mockReturnValue({
      data: { provider: 'wati', items: LIVE_ITEMS, error: null },
      isFetching: false,
      error: null,
      refresh: vi.fn(),
    });
    const onChange = vi.fn();

    render(
      <WatiChannelPicker connectionId="conn-wati" value="" onChange={onChange} />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Select a channel number/i }));
    fireEvent.click(await screen.findByText('+911234567890 · Main Channel'));
    expect(onChange).toHaveBeenCalledWith('+911234567890');
  });

  it('falls back to stored channel_numbers when live list is empty', async () => {
    mockedHook.mockReturnValue({
      data: { provider: 'wati', items: [], error: null },
      isFetching: false,
      error: null,
      refresh: vi.fn(),
    });
    mockedGetConnection.mockResolvedValue(makeConnection(STORED_CHANNELS));

    render(
      <WatiChannelPicker connectionId="conn-wati" value="" onChange={vi.fn()} />,
    );

    fireEvent.click(await screen.findByRole('button', { name: /Select a channel number/i }));
    expect(await screen.findByText('+919876543210')).toBeInTheDocument();
    expect(screen.getByText('+441234567890')).toBeInTheDocument();
  });

  it('shows free-text input when both live and stored lists are empty', async () => {
    mockedHook.mockReturnValue({
      data: { provider: 'wati', items: [], error: null },
      isFetching: false,
      error: null,
      refresh: vi.fn(),
    });
    mockedGetConnection.mockResolvedValue(makeConnection([]));

    const onChange = vi.fn();
    render(
      <WatiChannelPicker connectionId="conn-wati" value="" onChange={onChange} />,
    );

    await waitFor(() => expect(mockedGetConnection).toHaveBeenCalledWith('conn-wati'));
    const input = await screen.findByPlaceholderText(/\+91/i);
    expect(input).toBeInTheDocument();
    fireEvent.change(input, { target: { value: '+913333333333' } });
    expect(onChange).toHaveBeenCalledWith('+913333333333');
  });

  it('keeps an already-saved value selectable even when absent from the live list', async () => {
    mockedHook.mockReturnValue({
      data: { provider: 'wati', items: LIVE_ITEMS, error: null },
      isFetching: false,
      error: null,
      refresh: vi.fn(),
    });

    render(
      <WatiChannelPicker
        connectionId="conn-wati"
        value="+999000000000"
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: /\+999000000000/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /\+999000000000/ }));
    // Saved value appears in both the trigger label and the dropdown option row.
    const matches = await screen.findAllByText('+999000000000');
    expect(matches.length).toBeGreaterThanOrEqual(2);
  });
});
