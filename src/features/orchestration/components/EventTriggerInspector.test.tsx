import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/services/api/orchestrationTriggers', () => ({
  getEventCatalog: vi.fn(),
  listEventTriggers: vi.fn(),
  createEventTrigger: vi.fn(),
  updateEventTrigger: vi.fn(),
  deleteEventTrigger: vi.fn(),
  rotateEventTriggerToken: vi.fn(),
}));

vi.mock('@/services/notifications', () => ({
  notificationService: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

vi.mock('@/hooks', () => ({
  useCurrentAppId: () => 'inside-sales',
}));

import {
  createEventTrigger,
  getEventCatalog,
  listEventTriggers,
} from '@/services/api/orchestrationTriggers';
import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import { EventTriggerInspector } from './EventTriggerInspector';

function renderInspector() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <EventTriggerInspector />
    </QueryClientProvider>,
  );
}

function seedStore(workflowType: 'crm' | 'clinical' | null, workflowId: string | null) {
  useWorkflowBuilderStore.setState({ workflowType, workflowId });
}

const CRM_CATALOG = {
  workflowType: 'crm' as const,
  events: [
    { name: 'lead.created', label: 'Lead created' },
    { name: 'deal.stage_changed', label: 'Deal stage changed' },
  ],
};

const CLINICAL_CATALOG = {
  workflowType: 'clinical' as const,
  events: [
    { name: 'program.enrolled', label: 'Program enrolled' },
    { name: 'refill.due', label: 'Refill due' },
  ],
};

describe('EventTriggerInspector', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (listEventTriggers as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    useWorkflowBuilderStore.getState().reset();
  });

  it('gates the event-name catalog by the workflow type (crm)', async () => {
    seedStore('crm', 'wf-1');
    (getEventCatalog as ReturnType<typeof vi.fn>).mockResolvedValue(CRM_CATALOG);

    renderInspector();

    await waitFor(() =>
      expect(getEventCatalog).toHaveBeenCalledWith({
        workflowType: 'crm',
        appId: 'inside-sales',
      }),
    );
  });

  it('gates the event-name catalog by the workflow type (clinical)', async () => {
    seedStore('clinical', 'wf-2');
    (getEventCatalog as ReturnType<typeof vi.fn>).mockResolvedValue(CLINICAL_CATALOG);

    renderInspector();

    await waitFor(() =>
      expect(getEventCatalog).toHaveBeenCalledWith({
        workflowType: 'clinical',
        appId: 'inside-sales',
      }),
    );
  });

  it('renders every existing trigger binding (multi-binding list)', async () => {
    seedStore('crm', 'wf-1');
    (getEventCatalog as ReturnType<typeof vi.fn>).mockResolvedValue(CRM_CATALOG);
    (listEventTriggers as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: 't-1',
        workflowId: 'wf-1',
        kind: 'event',
        eventName: 'lead.created',
        vendor: 'frappe',
        webhookTokenMasked: 'wXyZ••••AbCd',
        webhookUrl: 'https://app.test/webhooks/event/frappe/abc',
        samplePayload: { lead_id: 1 },
        curlSnippet: 'curl ...',
        active: true,
        createdAt: '2026-05-23T00:00:00Z',
        updatedAt: '2026-05-23T00:00:00Z',
      },
      {
        id: 't-2',
        workflowId: 'wf-1',
        kind: 'event',
        eventName: 'deal.stage_changed',
        vendor: 'lsq',
        webhookTokenMasked: 'qRsT••••UvWx',
        webhookUrl: 'https://app.test/webhooks/event/lsq/def',
        samplePayload: { deal_id: 2 },
        curlSnippet: 'curl ...',
        active: false,
        createdAt: '2026-05-23T00:00:00Z',
        updatedAt: '2026-05-23T00:00:00Z',
      },
    ]);

    renderInspector();

    expect(await screen.findByText('lead.created')).toBeInTheDocument();
    expect(await screen.findByText('deal.stage_changed')).toBeInTheDocument();
  });

  it('renders the masked token for an existing trigger, never a plaintext secret', async () => {
    seedStore('crm', 'wf-1');
    (getEventCatalog as ReturnType<typeof vi.fn>).mockResolvedValue(CRM_CATALOG);
    (listEventTriggers as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: 't-1',
        workflowId: 'wf-1',
        kind: 'event',
        eventName: 'lead.created',
        vendor: 'webhook',
        webhookTokenMasked: 'wXyZ••••AbCd',
        webhookUrl: 'https://app.test/webhooks/event/webhook/abc',
        samplePayload: { hello: 'world' },
        curlSnippet: 'curl ...',
        active: true,
        createdAt: '2026-05-23T00:00:00Z',
        updatedAt: '2026-05-23T00:00:00Z',
      },
    ]);

    renderInspector();

    expect(await screen.findByText(/wXyZ••••AbCd/)).toBeInTheDocument();
  });

  it('creates a new binding and reveals the plaintext token exactly once', async () => {
    seedStore('crm', 'wf-1');
    (getEventCatalog as ReturnType<typeof vi.fn>).mockResolvedValue(CRM_CATALOG);
    (createEventTrigger as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 't-new',
      workflowId: 'wf-1',
      kind: 'event',
      eventName: 'lead.created',
      vendor: 'webhook',
      webhookToken: 'PLAINTEXT-TOKEN-SHOWN-ONCE',
      webhookUrl: 'https://app.test/webhooks/event/webhook/new',
      samplePayload: { hello: 'world' },
      curlSnippet: 'curl ...',
      active: true,
      createdAt: '2026-05-23T00:00:00Z',
      updatedAt: '2026-05-23T00:00:00Z',
    });

    renderInspector();

    const addButton = await screen.findByRole('button', { name: /add trigger/i });
    fireEvent.click(addButton);

    // Pick-or-type: open the event-name combobox and choose a catalog suggestion.
    const eventField = await screen.findByRole('button', { name: /pick or type an event/i });
    fireEvent.click(eventField);
    fireEvent.click(await screen.findByText('Lead created'));

    const saveButton = screen.getByRole('button', { name: /^create$/i });
    fireEvent.click(saveButton);

    await waitFor(() =>
      expect(createEventTrigger).toHaveBeenCalledWith('wf-1', {
        eventName: 'lead.created',
        vendor: 'webhook',
        active: true,
      }),
    );

    const reveal = await screen.findByText('PLAINTEXT-TOKEN-SHOWN-ONCE');
    expect(within(reveal.closest('div') as HTMLElement).getByText(/once/i)).toBeInTheDocument();
  });
});
