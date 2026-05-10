/**
 * Phase 2 (sherlock-builder) — context chip rendered inside `ChatInput`
 * above the textarea.
 *
 * Two visual modes:
 *   - `viewMode === 'edit'`: dismissible chip narrating "Editing: <wf>". The
 *     [×] hides the chip locally and signals `dismissNextPageContext` to
 *     the next message's `getPageContextSnapshot` call so the LLM doesn't
 *     receive the canvas for this turn only.
 *   - `viewMode === 'view'`: informational pill ("Viewing: <wf>"). No
 *     dismiss because the backend already declines to attach the authoring
 *     tool when viewing — chip is read-only signal to the user.
 *
 * No hex literals. No template-literal class concat. Self-contained.
 */
import { Pencil, Eye, X } from 'lucide-react';
import { cn } from '@/utils/cn';

import type { PageContext } from '@/features/orchestration/copilot/usePageContext';

interface BuilderContextChipProps {
  pageContext: Extract<PageContext, { kind: 'orchestration_builder' }>;
  onDismiss: () => void;
}

export function BuilderContextChip({ pageContext, onDismiss }: BuilderContextChipProps) {
  const isEdit = pageContext.viewMode === 'edit';
  const Icon = isEdit ? Pencil : Eye;

  const verb = isEdit ? 'Editing' : 'Viewing';
  const workflowName = pageContext.workflowName.trim() || 'workflow';

  const selectedNode = pageContext.selectedNodeId
    ? pageContext.definition.nodes.find((n) => n.id === pageContext.selectedNodeId)
    : null;
  const selectionLabel = selectedNode
    ? `${selectedNode.type}${selectedNode.id ? ` · ${selectedNode.id}` : ''}`
    : null;

  const hint = isEdit
    ? selectionLabel
      ? `selected: ${selectionLabel}`
      : 'no selection'
    : 'switch to Edit on the canvas to let me make changes';

  return (
    <div
      className={cn(
        'mx-3 mt-2 mb-1 flex items-center justify-between gap-2 rounded-md',
        'border px-2 py-1 text-[12px]',
        isEdit
          ? 'border-[var(--border-brand)] bg-[var(--surface-brand-subtle)] text-[var(--text-primary)]'
          : 'border-[var(--border-default)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]',
      )}
      role="status"
      aria-label={`${verb} ${workflowName}`}
      data-testid="builder-context-chip"
    >
      <div className="flex min-w-0 items-center gap-1.5">
        <Icon className="h-3.5 w-3.5 shrink-0" />
        <span className="font-medium truncate">{`${verb}: ${workflowName}`}</span>
        <span className="truncate text-[var(--text-muted)]">{`· ${hint}`}</span>
      </div>
      {isEdit ? (
        <button
          type="button"
          onClick={onDismiss}
          className={cn(
            'flex h-5 w-5 shrink-0 items-center justify-center rounded',
            'text-[var(--text-muted)] hover:text-[var(--text-primary)]',
            'hover:bg-[var(--bg-tertiary)] focus-visible:outline-none',
            'focus-visible:ring-1 focus-visible:ring-[var(--color-brand-accent)]',
          )}
          aria-label="Skip canvas context for next message"
          title="Skip canvas context for next message"
          data-testid="builder-context-chip-dismiss"
        >
          <X className="h-3 w-3" />
        </button>
      ) : null}
    </div>
  );
}
