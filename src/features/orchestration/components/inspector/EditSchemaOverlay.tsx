import { Braces, X } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { SchemaTable } from '@/features/evals/components/SchemaTable';
import type { EvaluatorOutputField } from '@/types';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  fields: EvaluatorOutputField[];
  onChange: (fields: EvaluatorOutputField[]) => void;
}

/** Inspector-level overlay: fills the AI agent inspector column (the parent
 *  container is relatively positioned), not a page-level slide-over. */
export function EditSchemaOverlay({ isOpen, onClose, fields, onChange }: Props) {
  if (!isOpen) return null;
  return (
    <div className="absolute inset-0 z-[var(--z-overlay)] flex flex-col bg-[var(--bg-primary)]">
        <div className="flex items-center gap-2.5 border-b border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-4 py-3">
          <span className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-default)] bg-[var(--surface-info)] text-[var(--color-info)]">
            <Braces className="h-4 w-4" aria-hidden="true" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[15px] font-semibold text-[var(--text-primary)]">
              Fields to extract
            </span>
            <span className="block text-[12px] text-[var(--text-muted)]">
              The structured fields the model must return, enforced as JSON Schema.
            </span>
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close schema editor"
            className="rounded p-1 text-[var(--text-muted)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <SchemaTable fields={fields} onChange={onChange} />
        </div>

        <div className="flex items-center justify-end border-t border-[var(--border-subtle)] px-4 py-3">
          <Button type="button" size="sm" variant="primary" onClick={onClose}>
            Done
          </Button>
        </div>
    </div>
  );
}
