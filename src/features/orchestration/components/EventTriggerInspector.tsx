import { useMemo, useState } from 'react';
import { ChevronDown, KeyRound, Plus, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { Combobox, type ComboboxOption } from '@/components/ui/Combobox';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { CopyButton } from '@/features/sherlock/components/CopyButton';
import { Select } from '@/components/ui/Select';
import { Switch } from '@/components/ui/Switch';
import {
  InspectorEmptyState,
  InspectorField,
  InspectorSection,
} from '@/features/orchestration/components/inspector/InspectorPrimitives';
import {
  useCreateEventTriggerMutation,
  useDeleteEventTriggerMutation,
  useEventCatalog,
  useEventTriggers,
  useRotateEventTriggerTokenMutation,
  useUpdateEventTriggerMutation,
} from '@/features/orchestration/queries/eventTriggers';
import type {
  EventTrigger,
  EventTriggerVendor,
} from '@/services/api/orchestrationTriggers';
import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import { decodeApiError, summarizeApiErrorBody } from '@/features/orchestration/contracts/errorDecoder';
import { notificationService } from '@/services/notifications';
import { useCurrentAppId } from '@/hooks';
import { cn } from '@/utils';

const VENDOR_OPTIONS: ReadonlyArray<{ value: EventTriggerVendor; label: string }> = [
  { value: 'webhook', label: 'Generic webhook' },
  { value: 'frappe', label: 'Frappe CRM' },
  { value: 'lsq', label: 'LeadSquared' },
  { value: 'mytatva', label: 'MyTatva' },
];

const VENDOR_LABELS: Record<EventTriggerVendor, string> = {
  webhook: 'Generic webhook',
  frappe: 'Frappe CRM',
  lsq: 'LeadSquared',
  mytatva: 'MyTatva',
};

export function EventTriggerInspector() {
  const workflowId = useWorkflowBuilderStore((s) => s.workflowId);
  const workflowType = useWorkflowBuilderStore((s) => s.workflowType);
  const appId = useCurrentAppId();

  const catalog = useEventCatalog(workflowType, appId);
  const triggersQuery = useEventTriggers(workflowId);

  const createMutation = useCreateEventTriggerMutation(workflowId);
  const [showCreate, setShowCreate] = useState(false);
  const [reveal, setReveal] = useState<string | null>(null);

  const catalogOptions = useMemo<ComboboxOption[]>(
    () =>
      (catalog.data?.events ?? []).map((name) => ({
        value: name,
        label: name,
      })),
    [catalog.data],
  );

  if (!workflowId) {
    return (
      <InspectorEmptyState>
        Save the workflow before adding event triggers.
      </InspectorEmptyState>
    );
  }

  const triggers = triggersQuery.data ?? [];

  return (
    <div className="flex flex-col gap-3">
      <InspectorSection
        title="Event triggers"
        description="Each trigger fires this workflow when the matching event arrives at its own webhook URL. A workflow can have several triggers."
        actions={
          <Button
            type="button"
            size="sm"
            variant="secondary"
            icon={Plus}
            onClick={() => setShowCreate(true)}
          >
            Add trigger
          </Button>
        }
      >
        {triggersQuery.isLoading ? (
          <InspectorEmptyState>Loading triggers…</InspectorEmptyState>
        ) : triggers.length === 0 ? (
          <InspectorEmptyState>
            No triggers yet. Add one to start firing this workflow from your system.
          </InspectorEmptyState>
        ) : (
          <div className="flex flex-col gap-2">
            {triggers.map((trigger) => (
              <TriggerCard
                key={trigger.id}
                trigger={trigger}
                workflowId={workflowId}
              />
            ))}
          </div>
        )}
      </InspectorSection>

      {showCreate ? (
        <CreateTriggerForm
          catalogOptions={catalogOptions}
          catalogLoading={catalog.isLoading}
          isSaving={createMutation.isPending}
          onCancel={() => setShowCreate(false)}
          onSubmit={(eventName, vendor, active) => {
            createMutation.mutate(
              { eventName, vendor, active },
              {
                onSuccess: (created) => {
                  setShowCreate(false);
                  setReveal(created.webhookUrl);
                  notificationService.success('Trigger created');
                },
                onError: (err) => {
                  notificationService.error(
                    summarizeApiErrorBody(decodeApiError(err), 'Could not create trigger'),
                  );
                },
              },
            );
          }}
        />
      ) : null}

      {reveal ? (
        <TokenRevealPanel webhookUrl={reveal} onDismiss={() => setReveal(null)} />
      ) : null}
    </div>
  );
}

function CreateTriggerForm({
  catalogOptions,
  catalogLoading,
  isSaving,
  onCancel,
  onSubmit,
}: {
  catalogOptions: ComboboxOption[];
  catalogLoading: boolean;
  isSaving: boolean;
  onCancel: () => void;
  onSubmit: (eventName: string, vendor: EventTriggerVendor, active: boolean) => void;
}) {
  const [eventName, setEventName] = useState('');
  const [query, setQuery] = useState('');
  const [vendor, setVendor] = useState<EventTriggerVendor>('webhook');
  const [active, setActive] = useState(true);

  // Pick-or-type: surface the typed query as a synthetic "Use" option so the
  // operator can bind an event the seed catalog doesn't list yet.
  const options = useMemo<ComboboxOption[]>(() => {
    const trimmed = query.trim();
    const matchesExisting = catalogOptions.some(
      (o) => o.value.toLowerCase() === trimmed.toLowerCase(),
    );
    if (!trimmed || matchesExisting) return catalogOptions;
    return [{ value: trimmed, label: `Use "${trimmed}"`, meta: 'custom' }, ...catalogOptions];
  }, [catalogOptions, query]);

  return (
    <InspectorSection title="New trigger">
      <InspectorField
        label="Event name"
        required
        description="Pick a suggested event for this workflow type, or type your own canonical name."
      >
        <Combobox
          value={eventName}
          onChange={setEventName}
          onSearchChange={setQuery}
          options={options}
          loading={catalogLoading}
          placeholder="Pick or type an event"
          size="sm"
        />
      </InspectorField>

      <InspectorField
        label="Source"
        description="Which system sends the event. Generic webhook expects an already-canonical payload; the others translate native payloads for you."
      >
        <Select
          value={vendor}
          onChange={(v) => setVendor(v as EventTriggerVendor)}
          options={VENDOR_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
          size="sm"
        />
      </InspectorField>

      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-[var(--text-primary)]">Active</span>
        <Switch checked={active} onCheckedChange={setActive} size="sm" />
      </div>

      <div className="flex items-center justify-end gap-2 pt-1">
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button
          type="button"
          size="sm"
          variant="primary"
          isLoading={isSaving}
          disabled={!eventName.trim() || isSaving}
          onClick={() => onSubmit(eventName.trim(), vendor, active)}
        >
          Create
        </Button>
      </div>
    </InspectorSection>
  );
}

function TriggerCard({
  trigger,
  workflowId,
}: {
  trigger: EventTrigger;
  workflowId: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [reveal, setReveal] = useState<string | null>(null);

  const updateMutation = useUpdateEventTriggerMutation(workflowId);
  const deleteMutation = useDeleteEventTriggerMutation(workflowId);
  const rotateMutation = useRotateEventTriggerTokenMutation(workflowId);

  const toggleActive = (next: boolean) => {
    updateMutation.mutate(
      { triggerId: trigger.id, body: { active: next } },
      {
        onError: (err) =>
          notificationService.error(
            summarizeApiErrorBody(decodeApiError(err), 'Could not update trigger'),
          ),
      },
    );
  };

  return (
    <div className="rounded-[var(--radius-default)] border border-[var(--border-default)] bg-[var(--bg-primary)] p-2.5">
      <div className="flex items-start justify-between gap-2">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
        >
          <ChevronDown
            className={cn(
              'h-3.5 w-3.5 shrink-0 text-[var(--text-muted)] transition-transform',
              expanded && 'rotate-180',
            )}
          />
          <span className="min-w-0">
            <span className="block truncate text-sm font-medium text-[var(--text-primary)]">
              {trigger.eventName ?? 'Unnamed event'}
            </span>
            <span className="block truncate text-xs text-[var(--text-secondary)]">
              {VENDOR_LABELS[trigger.vendor] ?? trigger.vendor}
            </span>
          </span>
        </button>
        <Switch
          checked={trigger.active}
          onCheckedChange={toggleActive}
          size="sm"
          aria-label={`Toggle ${trigger.eventName ?? 'trigger'} active`}
        />
      </div>

      {trigger.webhookTokenMasked ? (
        <div className="mt-1.5 flex items-center gap-1.5 pl-5 text-[11px] text-[var(--text-muted)]">
          <KeyRound className="h-3 w-3 shrink-0" />
          <code className="truncate">{trigger.webhookTokenMasked}</code>
        </div>
      ) : null}

      {expanded ? (
        <div className="mt-2.5 flex flex-col gap-2.5 border-t border-[var(--border-subtle)] pt-2.5">
          <ConnectPanel webhookUrl={trigger.webhookUrl} vendor={trigger.vendor} />
          <div className="flex items-center justify-between gap-2">
            <Button
              type="button"
              size="sm"
              variant="secondary"
              icon={KeyRound}
              isLoading={rotateMutation.isPending}
              onClick={() =>
                rotateMutation.mutate(
                  { triggerId: trigger.id },
                  {
                    onSuccess: (rotated) => {
                      setReveal(rotated.webhookUrl);
                      notificationService.success('Token rotated');
                    },
                    onError: (err) =>
                      notificationService.error(
                        summarizeApiErrorBody(decodeApiError(err), 'Could not rotate token'),
                      ),
                  },
                )
              }
            >
              Rotate token
            </Button>
            <Button
              type="button"
              size="sm"
              variant="danger-outline"
              icon={Trash2}
              iconOnly
              aria-label={`Delete ${trigger.eventName ?? 'trigger'}`}
              onClick={() => setConfirmDelete(true)}
            />
          </div>
          {reveal ? (
            <TokenRevealPanel webhookUrl={reveal} onDismiss={() => setReveal(null)} />
          ) : null}
        </div>
      ) : null}

      <ConfirmDialog
        isOpen={confirmDelete}
        title="Delete trigger?"
        description="This stops the workflow from firing on this event. The webhook URL will reject future calls."
        confirmLabel="Delete"
        variant="danger"
        isLoading={deleteMutation.isPending}
        onClose={() => setConfirmDelete(false)}
        onConfirm={() =>
          deleteMutation.mutate(
            { triggerId: trigger.id },
            {
              onSuccess: () => {
                setConfirmDelete(false);
                notificationService.success('Trigger deleted');
              },
              onError: (err) => {
                setConfirmDelete(false);
                notificationService.error(
                  summarizeApiErrorBody(decodeApiError(err), 'Could not delete trigger'),
                );
              },
            },
          )
        }
      />
    </div>
  );
}

// The backend translates each vendor's native payload to this canonical shape;
// for the identity `webhook` vendor it IS the expected request body.
const CANONICAL_SAMPLE = JSON.stringify(
  {
    recipients: [
      { recipient_id: 'lead-123', payload: { name: 'Jane Doe', phone: '+15551234567' } },
    ],
  },
  null,
  2,
);

function buildCurl(webhookUrl: string): string {
  return [
    `curl -X POST '${webhookUrl}' \\`,
    `  -H 'Content-Type: application/json' \\`,
    `  -d '${CANONICAL_SAMPLE.replace(/\s+/g, ' ')}'`,
  ].join('\n');
}

function ConnectPanel({
  webhookUrl,
  vendor,
}: {
  webhookUrl: string | null;
  vendor: EventTriggerVendor;
}) {
  const curlSnippet = webhookUrl ? buildCurl(webhookUrl) : null;
  return (
    <div className="flex flex-col gap-2.5">
      <div className="text-xs font-medium text-[var(--text-secondary)]">
        Connect your system
      </div>

      {webhookUrl ? (
        <FieldRow label="Webhook URL" copyText={webhookUrl}>
          <code className="block truncate text-[11px] text-[var(--text-primary)]">
            {webhookUrl}
          </code>
        </FieldRow>
      ) : (
        <p className="text-[11px] text-[var(--text-muted)]">
          Save the trigger to generate its webhook URL.
        </p>
      )}

      {vendor !== 'webhook' ? (
        <p className="text-[11px] text-[var(--text-muted)]">
          {VENDOR_LABELS[vendor]} posts its native payload — it is translated to the
          canonical shape automatically. The sample below shows that canonical target.
        </p>
      ) : null}

      <FieldRow label="Sample payload" copyText={CANONICAL_SAMPLE}>
        <pre className="max-h-40 overflow-auto rounded-[var(--radius-default)] bg-[var(--bg-tertiary)] p-2 text-[11px] text-[var(--text-primary)]">
          {CANONICAL_SAMPLE}
        </pre>
      </FieldRow>

      {curlSnippet ? (
        <FieldRow label="Test with curl" copyText={curlSnippet}>
          <pre className="max-h-40 overflow-auto rounded-[var(--radius-default)] bg-[var(--bg-tertiary)] p-2 text-[11px] text-[var(--text-primary)]">
            {curlSnippet}
          </pre>
        </FieldRow>
      ) : null}
    </div>
  );
}

function FieldRow({
  label,
  copyText,
  children,
}: {
  label: string;
  copyText?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="group flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
          {label}
        </span>
        {copyText ? <CopyButton text={copyText} /> : null}
      </div>
      {children}
    </div>
  );
}

function TokenRevealPanel({
  webhookUrl,
  onDismiss,
}: {
  webhookUrl: string | null;
  onDismiss: () => void;
}) {
  if (!webhookUrl) return null;
  return (
    <div className="flex flex-col gap-2 rounded-[var(--radius-default)] border border-[var(--border-warning)] bg-[var(--surface-warning)] p-2.5">
      <div className="text-xs font-medium text-[var(--color-warning)]">
        Your webhook URL — copy it into your system now.
      </div>
      <div className="flex items-center justify-between gap-2">
        <code className="min-w-0 flex-1 truncate text-[11px] text-[var(--text-primary)]">
          {webhookUrl}
        </code>
        <CopyButton text={webhookUrl} className="opacity-100" />
      </div>
      <div className="flex items-center justify-end">
        <Button type="button" size="sm" variant="ghost" onClick={onDismiss}>
          Done
        </Button>
      </div>
    </div>
  );
}
