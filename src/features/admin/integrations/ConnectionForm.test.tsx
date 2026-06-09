// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const createConnection = vi.fn();
const updateConnection = vi.fn();
const getProviderSchema = vi.fn();
vi.mock('@/services/api/orchestrationConnections', () => ({
  createConnection: (...a: unknown[]) => createConnection(...a),
  updateConnection: (...a: unknown[]) => updateConnection(...a),
  getProviderSchema: (...a: unknown[]) => getProviderSchema(...a),
}));

vi.mock('@/services/api/client', () => ({ ApiError: class extends Error {} }));
vi.mock('@/services/notifications', () => ({
  notificationService: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/stores/authStore', () => ({
  useAuthStore: (selector: (s: unknown) => unknown) =>
    selector({ user: { id: 'u1', appAccess: ['inside-sales', 'voice-rx'] } }),
}));

// Inert config form — we only assert scope controls + payload shape.
vi.mock('@/features/orchestration/components/DynamicConfigForm', () => ({
  DynamicConfigForm: () => null,
}));

import { ConnectionForm } from './ConnectionForm';

const SCHEMA = {
  provider: 'bolna',
  label: 'Bolna',
  supportsWebhook: true,
  kind: 'voice',
  jsonSchema: { type: 'object', properties: {} },
  fields: [],
};

beforeEach(() => {
  createConnection.mockReset().mockResolvedValue({ id: 'c1' });
  updateConnection.mockReset().mockResolvedValue({ id: 'c1' });
  getProviderSchema.mockReset().mockResolvedValue(SCHEMA);
});

describe('ConnectionForm app scope', () => {
  it('has a single Apps control and no Visibility / tenant-wide toggle', async () => {
    render(
      <ConnectionForm appId="inside-sales" onClose={vi.fn()} onSaved={vi.fn()} />,
    );
    expect(await screen.findByText('Apps')).toBeInTheDocument();
    expect(screen.queryByText('Visibility')).not.toBeInTheDocument();
    expect(screen.queryByText('Available to all apps')).not.toBeInTheDocument();
    expect(screen.queryByText('Also available to')).not.toBeInTheDocument();
  });

  it('sends home appId + appScopes on create and never visibility', async () => {
    render(
      <ConnectionForm appId="inside-sales" onClose={vi.fn()} onSaved={vi.fn()} />,
    );
    await screen.findByText('Apps');
    fireEvent.change(screen.getByPlaceholderText(/Bolna/i), {
      target: { value: 'Voice prod' },
    });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Create/i })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: /Create/i }));
    await waitFor(() => expect(createConnection).toHaveBeenCalled());
    const body = createConnection.mock.calls[0][0];
    expect(body.appId).toBe('inside-sales');
    expect(body).toHaveProperty('appScopes');
    expect(body.tenantWide).toBe(false);
    expect(body).not.toHaveProperty('visibility');
  });

  it('sends isDefault:true when the Make default switch is on', async () => {
    render(
      <ConnectionForm appId="inside-sales" onClose={vi.fn()} onSaved={vi.fn()} />,
    );
    await screen.findByText('Apps');
    fireEvent.change(screen.getByPlaceholderText(/Bolna/i), {
      target: { value: 'Voice prod' },
    });
    fireEvent.click(screen.getByLabelText('Make default'));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Create/i })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: /Create/i }));
    await waitFor(() => expect(createConnection).toHaveBeenCalled());
    expect(createConnection.mock.calls[0][0].isDefault).toBe(true);
  });

  it('shows the same Apps multiselect for a CRM provider', async () => {
    getProviderSchema.mockResolvedValue({ ...SCHEMA, provider: 'lsq', kind: 'crm_source' });
    render(
      <ConnectionForm
        appId="inside-sales"
        existing={
          {
            id: 'c1',
            tenantId: 't1',
            appId: 'inside-sales',
            tenantWide: false,
            appScopes: [],
            isDefault: false,
            provider: 'lsq',
            name: 'LSQ',
            active: true,
            lastUsedAt: null,
            webhookUrl: null,
            configRedacted: {},
            fields: [],
            createdBy: 'u1',
            createdAt: '',
            updatedAt: '',
          } as never
        }
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    );
    // Uniform: CRM gets the same multi "Apps" control as comm providers.
    expect(await screen.findByText('Apps')).toBeInTheDocument();
    expect(screen.queryByText('Available to all apps')).not.toBeInTheDocument();
  });
});
