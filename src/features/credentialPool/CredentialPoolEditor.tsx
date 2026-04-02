import { Plus, Trash2, Wifi } from 'lucide-react';

import { Button, Input } from '@/components/ui';

import type { CredentialPoolConfig, CredentialPoolEntry } from './types';

interface CredentialPoolEditorProps {
  config: CredentialPoolConfig;
  entries: CredentialPoolEntry[];
  onEntriesChange: (entries: CredentialPoolEntry[]) => void;
  onAddEntry: () => void;
  onTestEntry?: (entryId: string) => Promise<void>;
  onTestAll?: () => Promise<void>;
}

const SOURCE_LABELS: Record<CredentialPoolEntry['source'], string> = {
  seed: 'Seed',
  manual: 'Manual',
  csv: 'CSV',
  group: 'Group',
};

function statusClass(status: CredentialPoolEntry['testStatus']): string {
  switch (status) {
    case 'success':
      return 'text-[var(--color-success)]';
    case 'error':
      return 'text-[var(--color-error)]';
    case 'testing':
      return 'text-[var(--color-info)]';
    default:
      return 'text-[var(--text-muted)]';
  }
}

export function CredentialPoolEditor({
  config,
  entries,
  onEntriesChange,
  onAddEntry,
  onTestEntry,
  onTestAll,
}: CredentialPoolEditorProps) {
  const updateField = (entryId: string, fieldKey: string, value: string) => {
    onEntriesChange(
      entries.map((entry) => (
        entry.id === entryId
          ? {
              ...entry,
              values: {
                ...entry.values,
                [fieldKey]: value,
              },
              testStatus: 'idle',
              testMessage: null,
            }
          : entry
      )),
    );
  };

  const removeEntry = (entryId: string) => {
    onEntriesChange(entries.filter((entry) => entry.id !== entryId));
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h4 className="text-[13px] font-medium text-[var(--text-primary)]">{config.title}</h4>
          {config.description && (
            <p className="text-[11px] text-[var(--text-muted)]">{config.description}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {onTestAll && (
            <Button variant="secondary" size="sm" onClick={() => { void onTestAll(); }} icon={Wifi}>
              Test All
            </Button>
          )}
          <Button variant="secondary" size="sm" onClick={onAddEntry} icon={Plus}>
            Add Row
          </Button>
        </div>
      </div>

      <div className="space-y-3">
        {entries.map((entry) => (
          <div key={entry.id} className="rounded-[6px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span className="rounded-full bg-[var(--bg-tertiary)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]">
                  {SOURCE_LABELS[entry.source]}
                </span>
                <span className={`text-[11px] ${statusClass(entry.testStatus)}`}>
                  {entry.testStatus === 'idle' ? 'Not tested' : entry.testMessage || entry.testStatus}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {onTestEntry && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => { void onTestEntry(entry.id); }}
                    disabled={entry.testStatus === 'testing'}
                    isLoading={entry.testStatus === 'testing'}
                    icon={Wifi}
                  >
                    Test
                  </Button>
                )}
                <button
                  type="button"
                  onClick={() => removeEntry(entry.id)}
                  className="inline-flex items-center justify-center rounded-md border border-[var(--border-default)] p-2 text-[var(--text-secondary)] hover:bg-[var(--bg-primary)] hover:text-[var(--text-primary)] transition-colors"
                  aria-label="Remove credential row"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              {config.fields.map((field) => (
                <div key={field.key}>
                  <label className="block text-[12px] font-medium text-[var(--text-primary)] mb-1.5">
                    {field.label}
                  </label>
                  <Input
                    type={field.secret ? 'password' : 'text'}
                    value={entry.values[field.key] ?? ''}
                    placeholder={field.placeholder}
                    onChange={(e) => updateField(entry.id, field.key, e.target.value)}
                  />
                  {field.description && (
                    <p className="mt-1 text-[11px] text-[var(--text-muted)]">{field.description}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
