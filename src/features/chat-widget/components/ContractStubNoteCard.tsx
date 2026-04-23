import { AlertTriangle, CheckCircle2, FileText } from 'lucide-react';
import { cn } from '@/utils/cn';
import type { ContractStubNotePart, ContractStubNoteVariant } from '../types';

interface ContractStubNoteCardProps {
  part: ContractStubNotePart;
}

// Phase 8 — contract-stub proof pack renderer.
// Rendered solely because the artifact was dispatched on
// ``pack_id + contract_id`` (``contract_stub.note.v1``). Payload fields
// are already typed; this component never re-infers semantics.
const VARIANT_STYLES: Record<ContractStubNoteVariant, {
  container: string;
  icon: string;
  iconColor: string;
  badge: string;
}> = {
  plain: {
    container:
      'border-[color-mix(in_srgb,var(--border-secondary)_70%,transparent)] bg-[var(--bg-secondary)]',
    icon: 'FileText',
    iconColor: 'text-[var(--text-muted)]',
    badge: 'bg-[var(--bg-tertiary)] text-[var(--text-muted)]',
  },
  warning: {
    container:
      'border-[color-mix(in_srgb,var(--interactive-warning)_40%,transparent)] bg-[color-mix(in_srgb,var(--interactive-warning)_8%,var(--bg-secondary))]',
    icon: 'AlertTriangle',
    iconColor: 'text-[var(--interactive-warning)]',
    badge:
      'bg-[color-mix(in_srgb,var(--interactive-warning)_18%,transparent)] text-[var(--interactive-warning)]',
  },
  success: {
    container:
      'border-[color-mix(in_srgb,var(--interactive-success)_40%,transparent)] bg-[color-mix(in_srgb,var(--interactive-success)_8%,var(--bg-secondary))]',
    icon: 'CheckCircle2',
    iconColor: 'text-[var(--interactive-success)]',
    badge:
      'bg-[color-mix(in_srgb,var(--interactive-success)_18%,transparent)] text-[var(--interactive-success)]',
  },
};

export function ContractStubNoteCard({ part }: ContractStubNoteCardProps) {
  const styles = VARIANT_STYLES[part.variant] ?? VARIANT_STYLES.plain;
  const Icon = styles.icon === 'AlertTriangle'
    ? AlertTriangle
    : styles.icon === 'CheckCircle2'
      ? CheckCircle2
      : FileText;

  return (
    <div
      data-testid="contract-stub-note-card"
      data-pack-id="contract_stub"
      data-contract-id="contract_stub.note.v1"
      className={cn('rounded-2xl border p-3', styles.container)}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Icon className={cn('h-4 w-4 shrink-0', styles.iconColor)} />
          <span className="truncate text-sm font-semibold text-[var(--text-primary)]">
            {part.title}
          </span>
        </div>
        <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-semibold capitalize', styles.badge)}>
          {part.renderedVariant}
        </span>
      </div>
      <p className="mt-2 whitespace-pre-wrap text-[13px] text-[var(--text-primary)]">
        {part.body}
      </p>
      {part.truncated ? (
        <div className="mt-2 text-[11px] text-[var(--text-muted)]">
          Source truncated to fit the stub card.
        </div>
      ) : null}
    </div>
  );
}
