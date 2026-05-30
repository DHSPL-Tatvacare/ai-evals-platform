import type { CanvasPatchOp } from '@/features/orchestration/copilot/canvasPatchSchema';
import type { NodeTypeDescriptor } from '@/features/orchestration/types';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';

import { chatWidgetCopy } from '../copy';
import { ChatArtifactCard } from './ChatArtifactCard';

export type ChatCanvasChangeVariant = 'applied' | 'conflict' | 'blocked' | 'reverted';

export interface CanvasChangeChip {
  label: string;
}

export interface CanvasChangeSummary {
  summary: string;
  chips: CanvasChangeChip[];
}

/** Resolve a palette descriptor label for a node type; fall back to the raw
 *  type so the summary never goes blank, never hardcodes a node name. */
function labelFor(
  nodeType: string,
  descriptors: readonly NodeTypeDescriptor[],
): string {
  const desc = descriptors.find((d) => d.nodeType === nodeType);
  return desc?.displayLabel ?? desc?.label ?? nodeType;
}

/** Pure: build a plain-English summary + change chips from a patch op list,
 *  using palette descriptor labels for node names. No store import. */
export function buildCanvasChangeSummary(
  ops: readonly CanvasPatchOp[],
  descriptors: readonly NodeTypeDescriptor[],
): CanvasChangeSummary {
  const addedLabels: string[] = [];
  let addCount = 0;
  let connectCount = 0;
  let removeCount = 0;

  for (const op of ops) {
    if (op.op === 'add_node') {
      addCount += 1;
      addedLabels.push(labelFor(op.payload.node_type, descriptors));
    } else if (op.op === 'connect') {
      connectCount += 1;
    } else if (op.op === 'remove_node') {
      removeCount += 1;
    }
  }

  const parts: string[] = [];
  if (addedLabels.length > 0) {
    parts.push(`Added ${addedLabels.join(', ')}.`);
  }
  if (connectCount > 0) {
    parts.push(`Wired ${connectCount} connection${connectCount === 1 ? '' : 's'}.`);
  }
  if (removeCount > 0) {
    parts.push(`Removed ${removeCount} step${removeCount === 1 ? '' : 's'}.`);
  }

  const chips: CanvasChangeChip[] = [];
  if (addCount > 0) chips.push({ label: `+${addCount} steps` });
  if (connectCount > 0) chips.push({ label: `↻${connectCount} connections` });
  if (removeCount > 0) chips.push({ label: `-${removeCount} steps` });

  return { summary: parts.join(' '), chips };
}

export interface ChatCanvasChangeCardProps {
  variant: ChatCanvasChangeVariant;
  summary: string;
  rationale: string;
  chips: CanvasChangeChip[];
  nodeName?: string;
  onUndo?: () => void;
  onShowOnCanvas?: () => void;
  onRedoOnLatest?: () => void;
  onKeepAsIs?: () => void;
}

// Presentational canvas-change card. Knows nothing about the stream or store —
// the caller wires actions. Composes ChatArtifactCard + Badge + Button.
export function ChatCanvasChangeCard({
  variant,
  summary,
  rationale,
  chips,
  nodeName,
  onUndo,
  onShowOnCanvas,
  onRedoOnLatest,
  onKeepAsIs,
}: ChatCanvasChangeCardProps) {
  if (variant === 'applied') {
    return (
      <ChatArtifactCard
        kind="summary"
        title={chatWidgetCopy.cardTitleApplied}
        actions={
          <>
            {onUndo ? (
              <Button variant="ghost" size="sm" onClick={onUndo}>
                {chatWidgetCopy.undo}
              </Button>
            ) : null}
            {onShowOnCanvas ? (
              <Button variant="secondary" size="sm" onClick={onShowOnCanvas}>
                {chatWidgetCopy.showOnCanvas}
              </Button>
            ) : null}
          </>
        }
      >
        <div className="flex flex-col gap-3">
          {summary ? (
            <p className="text-sm text-[var(--text-primary)]">{summary}</p>
          ) : null}
          {chips.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {chips.map((chip) => (
                <Badge key={chip.label} variant="primary" size="sm">
                  {chip.label}
                </Badge>
              ))}
            </div>
          ) : null}
          <div className="flex flex-col gap-1 border-t border-[var(--border-subtle)] pt-2.5">
            <span className="text-[11px] font-medium uppercase tracking-wide text-[var(--text-muted)]">
              {chatWidgetCopy.rationaleLabel}
            </span>
            <p className="text-xs text-[var(--text-secondary)]">{rationale}</p>
          </div>
        </div>
      </ChatArtifactCard>
    );
  }

  if (variant === 'conflict') {
    return (
      <ChatArtifactCard
        kind="summary"
        title={chatWidgetCopy.cardTitleApplied}
        actions={
          <>
            {onRedoOnLatest ? (
              <Button variant="secondary" size="sm" onClick={onRedoOnLatest}>
                {chatWidgetCopy.redoOnLatest}
              </Button>
            ) : null}
            {onKeepAsIs ? (
              <Button variant="ghost" size="sm" onClick={onKeepAsIs}>
                {chatWidgetCopy.keepAsIs}
              </Button>
            ) : null}
          </>
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">{chatWidgetCopy.conflict}</p>
      </ChatArtifactCard>
    );
  }

  if (variant === 'reverted') {
    return (
      <ChatArtifactCard
        kind="summary"
        title={chatWidgetCopy.cardTitleApplied}
        actions={
          onRedoOnLatest ? (
            <Button variant="secondary" size="sm" onClick={onRedoOnLatest}>
              {chatWidgetCopy.redoOnLatest}
            </Button>
          ) : null
        }
      >
        <p className="text-sm text-[var(--text-secondary)]">{chatWidgetCopy.reverted}</p>
      </ChatArtifactCard>
    );
  }

  // blocked — non-destructive, no Undo/Redo.
  const blockedMessage = nodeName
    ? `${chatWidgetCopy.blocked} (${nodeName})`
    : chatWidgetCopy.blocked;
  return (
    <ChatArtifactCard kind="summary" title={chatWidgetCopy.cardTitleApplied}>
      <p className="text-sm text-[var(--text-secondary)]">{blockedMessage}</p>
    </ChatArtifactCard>
  );
}
