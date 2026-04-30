import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/services/api/orchestrationConnections', () => ({
  listConnections: vi.fn(),
}));

import { listConnections } from '@/services/api/orchestrationConnections';
import { ConnectionPicker } from '@/features/orchestration/components/connections/ConnectionPicker';

function makeConnection(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 'conn-1',
    tenantId: 't',
    appId: 'inside-sales',
    provider: 'bolna',
    name: 'Production Bolna',
    active: true,
    lastUsedAt: null,
    webhookUrl: null,
    configRedacted: {},
    fields: [],
    createdBy: 'u',
    createdAt: '',
    updatedAt: '',
    ...overrides,
  };
}

describe('ConnectionPicker', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  function renderPicker(props: React.ComponentProps<typeof ConnectionPicker>) {
    return render(
      <MemoryRouter>
        <ConnectionPicker {...props} />
      </MemoryRouter>,
    );
  }

  it('lists rows for a single-provider filter and selects one', async () => {
    (listConnections as ReturnType<typeof vi.fn>).mockResolvedValue([
      makeConnection({ id: 'a', name: 'Alpha' }),
      makeConnection({ id: 'b', name: 'Beta' }),
    ]);
    const onChange = vi.fn();
    renderPicker({
      appId: 'inside-sales',
      provider: 'bolna',
      value: '',
      onChange,
    });

    await waitFor(() =>
      expect(listConnections).toHaveBeenCalledWith({
        appId: 'inside-sales',
        providers: ['bolna'],
      }),
    );

    fireEvent.click(await screen.findByRole('button', { name: /Select a connection/ }));
    fireEvent.click(await screen.findByText('Beta'));
    expect(onChange).toHaveBeenCalledWith('b');
  });

  it('forwards multi-provider filter to the API client', async () => {
    (listConnections as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    renderPicker({
      appId: 'inside-sales',
      providers: ['aisensy', 'msg91'],
      value: '',
      onChange: vi.fn(),
    });

    await waitFor(() =>
      expect(listConnections).toHaveBeenCalledWith({
        appId: 'inside-sales',
        providers: ['aisensy', 'msg91'],
      }),
    );
  });

  it('renders empty-state with a "+ New Connection" link when no rows match', async () => {
    (listConnections as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    renderPicker({
      appId: 'inside-sales',
      provider: 'bolna',
      value: '',
      onChange: vi.fn(),
    });

    expect(await screen.findByText('+ New Connection')).toBeInTheDocument();
    expect(
      screen.getByText('+ New Connection').closest('a'),
    ).toHaveAttribute(
      'href',
      '/inside-sales/orchestration/connections',
    );
  });
});
