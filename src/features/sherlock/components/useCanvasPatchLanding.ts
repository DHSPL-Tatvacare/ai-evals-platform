/** Stateful bridge that lands a typed `canvas_patch` chat part onto the live
 *  builder store exactly once, then derives the card variant + action wiring
 *  the chat-widget canvas-change card renders. Idempotent on `part.id` — a
 *  re-render or SSE replay never re-applies (the store no-ops a repeat). */
import { useEffect, useRef, useState } from 'react';

import { applyCanvasPatch } from '@/features/orchestration/copilot/canvasPatchApplier';
import type { ApplyCanvasPatchResult } from '@/features/orchestration/copilot/canvasPatchApplier';
import type { CanvasPatchOp } from '@/features/orchestration/copilot/canvasPatchSchema';
import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import {
  buildCanvasChangeSummary,
  type CanvasChangeChip,
  type ChatCanvasChangeVariant,
} from '@/features/chat-widget/components/ChatCanvasChangeCard';
import { chatWidgetCopy } from '@/features/chat-widget/copy';

import type { CanvasPatchPart } from '../generated/sherlockContract';

/** What the bridge tells the card to render. */
export type CanvasPatchView = 'card' | 'stopped' | 'reverted' | 'hidden';

export interface CanvasPatchLanding {
  view: CanvasPatchView;
  variant: ChatCanvasChangeVariant;
  summary: string;
  rationale: string;
  chips: CanvasChangeChip[];
  /** Surfaced on `config_invalid` so the blocked card names the offending node. */
  nodeName?: string;
  /** Inline muted note for an aborted apply ("Stopped — applied N of M steps"). */
  stoppedNote: string | null;
  onUndo(): void;
  onShowOnCanvas(): void;
  onRedoOnLatest(): void;
  onKeepAsIs(): void;
}

/** Map the applier's discriminated result onto the card variant. `applied`
 *  flips to the success card; concurrency drift is a recoverable `conflict`;
 *  every other failure is a non-destructive `blocked`. */
function variantForResult(
  result: ApplyCanvasPatchResult | undefined,
): ChatCanvasChangeVariant {
  switch (result?.kind) {
    case 'applied':
      return 'applied';
    case 'hash_mismatch':
      return 'conflict';
    default:
      // version_mismatch | workflow_mismatch | parse_error | config_invalid
      return 'blocked';
  }
}

export function useCanvasPatchLanding(part: CanvasPatchPart): CanvasPatchLanding {
  const landCanvasPatch = useWorkflowBuilderStore((s) => s.landCanvasPatch);
  const applyInverse = useWorkflowBuilderStore((s) => s.applyInverse);
  const markChanged = useWorkflowBuilderStore((s) => s.markChanged);
  const paletteCatalog = useWorkflowBuilderStore((s) => s.paletteCatalog);
  const record = useWorkflowBuilderStore((s) => s.canvasEdits[part.id]);

  // Local view-state the card flips through (revert / keep / redo-conflict).
  // The store stays the source of truth for the applied edit; this is the
  // per-part presentation overlay only.
  const [override, setOverride] = useState<'reverted' | 'hidden' | 'conflict' | null>(null);

  // The store records a canvasEdits entry ONLY on `applied`; every non-applied
  // kind (hash_mismatch / version_mismatch / config_invalid / aborted /
  // parse_error) returns the result but persists nothing. So the variant must
  // come from landCanvasPatch's resolved RETURN value, not canvasEdits[part.id].
  const [landed, setLanded] = useState<ApplyCanvasPatchResult | undefined>();

  // Land exactly once per part. The store is idempotent on part.id, but the
  // ref keeps a re-render / replay from even re-invoking the async action.
  const landedRef = useRef(false);
  useEffect(() => {
    if (landedRef.current) return;
    landedRef.current = true;
    void landCanvasPatch(part.id, part.patch).then((r) => {
      if (r) setLanded(r);
    });
  }, [part.id, part.patch, landCanvasPatch]);

  const result = landed;
  // canvasEdits only carries the applied edit's changed nodes for re-flashing.
  const changedNodeIds = record?.changedNodeIds ?? [];

  // The contract's loose op shape is structurally the schema's discriminated
  // union (same backend Pydantic source); buildCanvasChangeSummary reads only
  // op.op + payload.node_type, both present on either shape.
  const ops = (part.patch.ops ?? []) as unknown as readonly CanvasPatchOp[];
  const { summary, chips } = buildCanvasChangeSummary(ops, paletteCatalog);
  const rationale = part.patch.rationale ?? '';

  const baseVariant = variantForResult(result);
  const variant: ChatCanvasChangeVariant =
    override === 'reverted'
      ? 'reverted'
      : override === 'conflict'
        ? 'conflict'
        : baseVariant;

  const nodeName =
    result?.kind === 'config_invalid' ? result.nodeId : undefined;

  const stoppedNote =
    result?.kind === 'aborted'
      ? chatWidgetCopy.stoppedTemplate({
          applied: result.opsApplied,
          total: ops.length,
        })
      : null;

  let view: CanvasPatchView;
  if (override === 'hidden') {
    view = 'hidden';
  } else if (override === 'reverted') {
    view = 'reverted';
  } else if (stoppedNote) {
    view = 'stopped';
  } else {
    view = 'card';
  }

  const onUndo = () => {
    applyInverse(part.id);
    setOverride('reverted');
  };

  const onShowOnCanvas = () => {
    markChanged(changedNodeIds);
  };

  // Best-effort redo against the live canvas. On a fresh hash mismatch we flip
  // the card to conflict; we never invent a new store action for this.
  const onRedoOnLatest = () => {
    void applyCanvasPatch(part.patch).then((redo) => {
      if (redo.kind === 'hash_mismatch') {
        setOverride('conflict');
      } else if (redo.kind === 'applied') {
        setOverride(null);
        markChanged([
          ...redo.addedNodeIds,
          ...redo.editedNodeIds,
          ...redo.removedNodeIds,
        ]);
      }
    });
  };

  const onKeepAsIs = () => {
    setOverride('hidden');
  };

  return {
    view,
    variant,
    summary,
    rationale,
    chips,
    nodeName,
    stoppedNote,
    onUndo,
    onShowOnCanvas,
    onRedoOnLatest,
    onKeepAsIs,
  };
}
