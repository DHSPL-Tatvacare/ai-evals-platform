/**
 * Persistent canvas-context chip rendered inside `ChatInput`.
 *
 * One card, two visual states driven by `workflowBuilderStore.canvasContextEnabled`:
 *   - On — bold card (solid surface + gradient hairline): status dot +
 *     "Editing · {workflow}" (verb reflects viewMode), a right
 *     workflow-type badge, and the Canvas Switch. An info line below derives
 *     the flow shape, or — when a node is selected — a "Focused on: {label}"
 *     scope chip with a clear control.
 *   - Off — muted card, switch left, a single "answering generally" line.
 *
 * Every label is derived (workflow type → badge, node type → descriptor
 * label, node categories → info line). No hardcoded node names, no hex.
 */
import { X } from 'lucide-react';

import { cn } from '@/utils/cn';
import { Badge } from '@/components/ui/Badge';
import { Switch } from '@/components/ui/Switch';
import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import type { NodeTypeDescriptor } from '@/features/orchestration/types';
import type { PageContext } from '@/features/orchestration/copilot/usePageContext';

import { chatWidgetCopy } from '../copy';

interface BuilderContextChipProps {
  pageContext: Extract<PageContext, { kind: 'orchestration_builder' }>;
  working: boolean;
}

const WORKFLOW_TYPE_LABEL: Record<'crm' | 'clinical', string> = {
  crm: 'CRM',
  clinical: 'Clinical',
};

/** Resolve a palette descriptor label for a node type; fall back to the raw
 *  type so the chip never goes blank, never hardcodes a node name. */
function labelFor(nodeType: string, catalog: readonly NodeTypeDescriptor[]): string {
  const desc = catalog.find((d) => d.nodeType === nodeType);
  return desc?.displayLabel ?? desc?.label ?? nodeType;
}

interface InfoLineShape {
  steps: number;
  count: number;
  category: string;
}

/** Derive the flow-shape info line: total steps + the dominant display
 *  category and its count, resolved through the palette catalog. */
function deriveInfoLine(
  nodeTypes: readonly string[],
  catalog: readonly NodeTypeDescriptor[],
): InfoLineShape {
  const steps = nodeTypes.length;
  const byCategory = new Map<string, number>();
  for (const nodeType of nodeTypes) {
    const desc = catalog.find((d) => d.nodeType === nodeType);
    const category = desc?.displayCategory ?? 'step';
    byCategory.set(category, (byCategory.get(category) ?? 0) + 1);
  }
  let category = 'step';
  let count = 0;
  for (const [cat, n] of byCategory) {
    if (n > count) {
      category = cat;
      count = n;
    }
  }
  return { steps, count, category };
}

export function BuilderContextChip({ pageContext, working }: BuilderContextChipProps) {
  const canvasOn = useWorkflowBuilderStore((s) => s.canvasContextEnabled);
  const setCanvasContextEnabled = useWorkflowBuilderStore((s) => s.setCanvasContextEnabled);
  const clearSelection = useWorkflowBuilderStore((s) => s.clearSelection);
  const paletteCatalog = useWorkflowBuilderStore((s) => s.paletteCatalog);

  const isEdit = pageContext.viewMode === 'edit';
  const verb = isEdit ? 'Editing' : 'Viewing';
  const workflowName = pageContext.workflowName.trim() || 'Untitled workflow';
  const typeLabel = WORKFLOW_TYPE_LABEL[pageContext.workflowType];

  const selectedNode = pageContext.selectedNodeId
    ? pageContext.definition.nodes.find((n) => n.id === pageContext.selectedNodeId)
    : null;

  const headerLabel = working ? chatWidgetCopy.workingLabel : `${verb} · ${workflowName}`;

  if (!canvasOn) {
    return (
      <div
        className={cn(
          'flex items-center gap-2 rounded-md border px-2 py-1.5 text-[12px]',
          'border-[var(--border-default)] bg-[var(--bg-primary)]',
        )}
        data-testid="builder-context-chip"
        data-canvas-on="false"
      >
        <span className="truncate text-[var(--text-muted)]">
          {chatWidgetCopy.canvasOffLine}
        </span>
        <Switch
          className="ml-auto shrink-0"
          size="sm"
          checked={false}
          onCheckedChange={() => setCanvasContextEnabled(true)}
          aria-label={chatWidgetCopy.canvasToggleLabel}
          data-testid="builder-context-chip-switch"
        />
      </div>
    );
  }

  const infoLine = deriveInfoLine(
    pageContext.definition.nodes.map((n) => n.type),
    paletteCatalog,
  );

  return (
    <div
      className={cn(
        'rounded-md border bg-[var(--bg-primary)] p-px',
        'bg-[var(--gradient-flow-border)]',
      )}
      data-testid="builder-context-chip"
      data-canvas-on="true"
    >
      <div className="rounded-[5px] bg-[var(--bg-primary)] px-2 py-1.5">
        <div className="flex items-center gap-1.5 text-[12px]">
          <span className="truncate font-medium text-[var(--text-primary)]">
            {headerLabel}
          </span>
          <span className="ml-auto flex shrink-0 items-center gap-1.5">
            <Badge variant="neutral" size="sm">
              {typeLabel}
            </Badge>
            <Switch
              size="sm"
              checked
              onCheckedChange={() => setCanvasContextEnabled(false)}
              aria-label={chatWidgetCopy.canvasToggleLabel}
              data-testid="builder-context-chip-switch"
            />
          </span>
        </div>

        <div className="mt-1 flex items-center gap-1.5 text-[11px] text-[var(--text-secondary)]">
          {selectedNode ? (
            <span
              className={cn(
                'inline-flex items-center gap-1 rounded-sm px-1.5 py-px',
                'border border-[var(--border-brand)] bg-[var(--surface-brand-subtle)]',
                'text-[var(--text-brand)]',
              )}
              data-testid="builder-context-chip-scope"
            >
              <span className="text-[var(--text-muted)]">
                {chatWidgetCopy.scopeFocusedPrefix}
              </span>
              <span className="font-medium">{labelFor(selectedNode.type, paletteCatalog)}</span>
              <button
                type="button"
                onClick={() => clearSelection()}
                className={cn(
                  'flex h-3.5 w-3.5 items-center justify-center rounded-sm',
                  'text-[var(--text-muted)] hover:text-[var(--text-primary)]',
                  'focus-visible:outline-none focus-visible:ring-1',
                  'focus-visible:ring-[var(--color-brand-accent)]',
                )}
                aria-label="Clear focus"
                data-testid="builder-context-chip-clear-scope"
              >
                <X className="h-2.5 w-2.5" />
              </button>
            </span>
          ) : (
            <span className="truncate text-[var(--text-muted)]">
              {chatWidgetCopy.infoLineTemplate(infoLine)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
