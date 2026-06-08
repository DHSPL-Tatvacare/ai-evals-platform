import { useState } from 'react';
import { X } from 'lucide-react';

import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { RightSlideOverShell } from '@/components/ui/RightSlideOverShell';
import { useCrmMappingDraftStore } from '@/stores/crmMappingDraftStore';

import { useCrmFieldValues } from '../queries/crmSourceQueries';

interface Props {
  connectionId: string;
  recordType: string | null;
}

/** L2 — map every value the CRM emits for a field to a canonical value. Blank = keep raw. */
export function CrmValueMapEditor({ connectionId, recordType }: Props) {
  const field = useCrmMappingDraftStore((s) => s.valueMapField);
  const binding = useCrmMappingDraftStore((s) => (field ? s.bindings[field] : undefined));
  const setValueMap = useCrmMappingDraftStore((s) => s.setValueMap);
  const close = useCrmMappingDraftStore((s) => s.closeValueMap);

  if (!field || !binding) return null;

  return (
    <RightSlideOverShell isOpen onClose={close} zIndexClassName="z-[var(--z-popover)]">
      <div className="flex shrink-0 items-start justify-between gap-4 border-b border-[var(--border-default)] bg-[var(--bg-secondary)] px-6 py-4">
        <div className="min-w-0">
          <h3 className="text-[15px] font-semibold text-[var(--text-primary)]">Map values</h3>
          <p className="truncate text-[12px] text-[var(--text-secondary)]">
            {binding.semanticKey} · from <span className="font-mono">{binding.sourceField}</span>
          </p>
        </div>
        <button
          onClick={close}
          className="text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)]"
          aria-label="Close"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* key={field}: remount with a fresh draft when a different field opens (no reset effect). */}
      <ValueMapForm
        key={field}
        connectionId={connectionId}
        recordType={recordType}
        field={field}
        initial={binding.valueMap ?? {}}
        onCommit={(map) => {
          setValueMap(field, Object.keys(map).length ? map : null);
          close();
        }}
        onCancel={close}
      />
    </RightSlideOverShell>
  );
}

interface FormProps {
  connectionId: string;
  recordType: string | null;
  field: string;
  initial: Record<string, string>;
  onCommit: (map: Record<string, string>) => void;
  onCancel: () => void;
}

function ValueMapForm({ connectionId, recordType, field, initial, onCommit, onCancel }: FormProps) {
  const [draftMap, setDraftMap] = useState<Record<string, string>>(initial);
  const valuesQuery = useCrmFieldValues(connectionId, recordType, field);
  const observed = valuesQuery.data?.values ?? [];
  const mappedCount = observed.filter((v) => (draftMap[v] ?? '').trim().length > 0).length;

  function commit() {
    const cleaned: Record<string, string> = {};
    for (const [k, v] of Object.entries(draftMap)) {
      if (v.trim()) cleaned[k] = v.trim();
    }
    onCommit(cleaned);
  }

  return (
    <>
      <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
        <Alert variant="info">
          Map every value the CRM sends to a canonical value. Leave a row blank to keep the value
          as-is.
        </Alert>

        <div className="flex items-center justify-between text-[12px] text-[var(--text-secondary)]">
          <span>Observed values</span>
          <span>
            {mappedCount} of {observed.length} mapped
          </span>
        </div>

        {valuesQuery.isLoading ? (
          <p className="text-[13px] text-[var(--text-muted)]">Loading values…</p>
        ) : observed.length === 0 ? (
          <p className="text-[13px] text-[var(--text-muted)]">
            No values have landed yet. Run a sync, then return to map them.
          </p>
        ) : (
          <div className="space-y-2">
            {observed.map((value) => (
              <div key={value} className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
                <code className="truncate rounded-[6px] bg-[var(--bg-secondary)] px-2 py-1.5 text-[12px] text-[var(--text-primary)]">
                  {value}
                </code>
                <span className="text-[var(--text-muted)]">→</span>
                <Input
                  value={draftMap[value] ?? ''}
                  onChange={(e) => setDraftMap({ ...draftMap, [value]: e.target.value })}
                  placeholder="canonical (blank = keep)"
                />
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex shrink-0 items-center justify-end gap-2 border-t border-[var(--border-default)] bg-[var(--bg-secondary)] px-6 py-4">
        <Button variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button onClick={commit}>Done</Button>
      </div>
    </>
  );
}
