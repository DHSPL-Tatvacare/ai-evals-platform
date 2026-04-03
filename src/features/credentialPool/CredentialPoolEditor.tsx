import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, Plus, Trash2, Wifi } from 'lucide-react';

import { Button, EmptyState, Input } from '@/components/ui';

import type { CredentialPoolConfig, CredentialPoolEntry } from './types';
import { isCredentialEntryComplete } from './utils';

interface CredentialPoolEditorProps {
  config: CredentialPoolConfig;
  entries: CredentialPoolEntry[];
  onEntriesChange: (entries: CredentialPoolEntry[]) => void;
  onAddEntry: () => void;
  onUploadCsv?: () => void;
  onOpenManage?: () => void;
  onTestEntry?: (entryId: string) => Promise<void>;
  onTestAll?: () => Promise<void>;
}

const SOURCE_LABELS: Record<CredentialPoolEntry['source'], string> = {
  seed: 'From Settings',
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
  onUploadCsv,
  onOpenManage,
  onTestEntry,
  onTestAll,
}: CredentialPoolEditorProps) {
  const [expandedEntryIds, setExpandedEntryIds] = useState<Record<string, boolean>>({});
  const requiredFields = useMemo(
    () => config.fields.filter((field) => field.required !== false),
    [config.fields],
  );
  const primaryFieldLabel = useMemo(
    () => config.fields.find((field) => field.key === config.primaryFieldKey)?.label ?? 'Identity',
    [config.fields, config.primaryFieldKey],
  );

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

  const toggleEntry = (entryId: string) => {
    setExpandedEntryIds((current) => ({
      ...current,
      [entryId]: !current[entryId],
    }));
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
          <Button
            variant="secondary"
            size="sm"
            onClick={onAddEntry}
            icon={Plus}
            iconOnly
            aria-label="Add credential row"
          />
          {onUploadCsv && (
            <Button variant="secondary" size="sm" onClick={onUploadCsv}>
              Upload
            </Button>
          )}
          {onOpenManage && (
            <Button variant="secondary" size="sm" onClick={onOpenManage}>
              Manage
            </Button>
          )}
          {onTestAll && (
            <Button variant="secondary" size="sm" onClick={() => { void onTestAll(); }} icon={Wifi}>
              Test All
            </Button>
          )}
        </div>
      </div>

      {entries.length === 0 ? (
        <EmptyState
          icon={Plus}
          title="No credential rows yet"
          description="Start with a row here, or use Upload / Manage when you need bulk credential workflows."
          className="py-12"
          action={{ label: 'Add Row', onClick: onAddEntry }}
        />
      ) : (
        <div className="space-y-3">
          {entries.map((entry, index) => {
            const isComplete = isCredentialEntryComplete(entry, config.fields);
            const isExpanded = expandedEntryIds[entry.id] ?? (
              entries.length === 1
              || !isComplete
              || entry.testStatus === 'error'
            );
            const filledRequiredCount = requiredFields.filter((field) => Boolean(entry.values[field.key]?.trim())).length;
            const primaryValue = entry.values[config.primaryFieldKey]?.trim();

            return (
              <div key={entry.id} className="rounded-[6px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
                <div className="flex items-start justify-between gap-3">
                  <button
                    type="button"
                    onClick={() => toggleEntry(entry.id)}
                    className="flex min-w-0 flex-1 items-start gap-3 text-left"
                  >
                    {isExpanded ? (
                      <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-[var(--text-muted)]" />
                    ) : (
                      <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-[var(--text-muted)]" />
                    )}

                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-full bg-[var(--bg-tertiary)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]">
                          {SOURCE_LABELS[entry.source]}
                        </span>
                        <span className="text-sm font-medium text-[var(--text-primary)]">
                          {primaryValue || `Credential Row ${index + 1}`}
                        </span>
                        <span className={`text-[11px] ${statusClass(entry.testStatus)}`}>
                          {entry.testStatus === 'idle' ? 'Not tested' : entry.testMessage || entry.testStatus}
                        </span>
                      </div>

                      <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                        {isComplete
                          ? `${primaryFieldLabel} is ready for execution.`
                          : `${filledRequiredCount}/${requiredFields.length} required fields completed.`}
                      </p>
                    </div>
                  </button>

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

                {isExpanded && (
                  <div className="mt-3 border-t border-[var(--border-subtle)] pt-3">
                    <div className="grid gap-3 md:grid-cols-2">
                      {config.fields.map((field) => (
                        <div key={field.key}>
                          <label className="mb-1.5 block text-[12px] font-medium text-[var(--text-primary)]">
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
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
