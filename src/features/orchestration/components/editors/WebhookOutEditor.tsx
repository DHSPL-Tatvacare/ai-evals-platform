import { Plus, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import type { AttemptPolicy, StructuredRequestBody } from '@/features/orchestration/types';
import { ConnectionPicker } from '@/features/admin/integrations/ConnectionPicker';

import {
  InspectorCard,
  InspectorEmptyState,
  InspectorField,
  InspectorSection,
} from '../inspector/InspectorPrimitives';
import { AttemptPolicyEditor } from './AttemptPolicyEditor';
import { StructuredRequestBodyEditor } from './StructuredRequestBodyEditor';

const METHOD_OPTIONS = [
  { value: 'POST', label: 'POST' },
  { value: 'PUT', label: 'PUT' },
];

const BODY_HELP = (
  <>
    Structured request body. Leaves can be JSON literals or payload references
    like <code>{'{ "$payload": "first_name" }'}</code>. Use{' '}
    <code>recipient_id</code> to reference the recipient&apos;s id.
  </>
);

interface WebhookConfig {
  connection_id?: string | null;
  url?: string;
  method?: 'POST' | 'PUT';
  headers?: Record<string, string>;
  body?: StructuredRequestBody;
  timeout_seconds?: number;
  attempt_policy?: AttemptPolicy;
}

interface Props {
  value: Record<string, unknown>;
  onChange(next: Record<string, unknown>): void;
  appId?: string;
}

export function WebhookOutEditor({ value, onChange, appId }: Props) {
  const cfg = value as WebhookConfig;
  const headers = (cfg.headers ?? {}) as Record<string, string>;
  const headerEntries = Object.entries(headers);

  const patch = (next: Partial<WebhookConfig>) =>
    onChange({ ...value, ...next });

  const setHeader = (oldKey: string, newKey: string, val: string) => {
    const next: Record<string, string> = {};
    for (const [k, v] of Object.entries(headers)) {
      next[k === oldKey ? newKey : k] = k === oldKey ? val : v;
    }
    patch({ headers: next });
  };

  const removeHeader = (key: string) => {
    const next = { ...headers };
    delete next[key];
    patch({ headers: next });
  };

  const addHeader = () => {
    // Find a unique placeholder key so multiple blank rows don't collide.
    let candidate = '';
    let i = 0;
    do { candidate = `header${i === 0 ? '' : i}`; i++; } while (candidate in headers);
    patch({ headers: { ...headers, [candidate]: '' } });
  };

  return (
    <div className="flex flex-col gap-3">
      {/* Endpoint */}
      <InspectorSection title="Endpoint">
        {appId ? (
          <InspectorField label="Connection" description="Optional reusable webhook connection for base URL and auth header.">
            <ConnectionPicker
              appId={appId}
              provider="webhook"
              value={typeof cfg.connection_id === 'string' ? cfg.connection_id : ''}
              onChange={(next) => patch({ connection_id: next || null })}
            />
          </InspectorField>
        ) : null}
        <InspectorField label="URL" required>
          <Input
            value={cfg.url ?? ''}
            onChange={(e) => patch({ url: e.target.value })}
            placeholder="https://api.example.com/webhook"
          />
        </InspectorField>
        <InspectorField label="Method">
          <Select
            value={cfg.method ?? 'POST'}
            onChange={(next) => patch({ method: next as 'POST' | 'PUT' })}
            options={METHOD_OPTIONS}
            side="top"
          />
        </InspectorField>
      </InspectorSection>

      {/* Headers */}
      <InspectorSection title="Headers">
        {headerEntries.length === 0 ? (
          <InspectorEmptyState>No headers — click Add to insert one.</InspectorEmptyState>
        ) : null}
        {headerEntries.map(([key, val]) => (
          <InspectorCard key={key} className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <Input
                value={key}
                onChange={(e) => setHeader(key, e.target.value, val)}
                placeholder="Header name"
                className="flex-1"
              />
              <button
                type="button"
                onClick={() => removeHeader(key)}
                className="shrink-0 rounded-[var(--radius-default)] border border-[var(--border-default)] p-2 text-[var(--text-muted)] transition-colors hover:border-[var(--color-error)]/30 hover:bg-[var(--color-error)]/5 hover:text-[var(--color-error)]"
                aria-label={`Remove ${key} header`}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
            <Input
              value={val}
              onChange={(e) => setHeader(key, key, e.target.value)}
              placeholder="Value"
            />
          </InspectorCard>
        ))}
        <Button variant="secondary" size="sm" onClick={addHeader}>
          <Plus className="mr-1 h-3.5 w-3.5" />
          Add header
        </Button>
      </InspectorSection>

      {/* Body */}
      <InspectorSection title="Body" description={BODY_HELP}>
        <StructuredRequestBodyEditor
          value={cfg.body as StructuredRequestBody | undefined}
          onChange={(next) => patch({ body: next })}
        />
      </InspectorSection>

      {/* Timeout & Retry */}
      <InspectorSection title="Timeout & Retry">
        <InspectorField label="Timeout (seconds)">
          <Input
            type="number"
            min={1}
            max={300}
            value={cfg.timeout_seconds ?? 10}
            onChange={(e) =>
              patch({ timeout_seconds: Number(e.target.value) || 10 })
            }
          />
        </InspectorField>
        <InspectorField label="Attempt policy">
          <AttemptPolicyEditor
            value={cfg.attempt_policy}
            onChange={(next) => patch({ attempt_policy: next })}
          />
        </InspectorField>
      </InspectorSection>
    </div>
  );
}
