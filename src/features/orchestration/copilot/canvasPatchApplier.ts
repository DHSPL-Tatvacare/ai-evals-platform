/**
 * Phase 2 (sherlock-builder) — receives a `CanvasPatch` off the chat stream
 * and translates each op into a `workflowBuilderStore` mutation.
 *
 * Behaviour spec (from the design doc + implementation plan):
 *   1. Validate via Zod. Drift surfaces as a chat-thread message; never throws.
 *   2. Optimistic-concurrency check: `patch.base_data_hash ===
 *      workflowBuilderStore.getState().currentDataHash`. On mismatch, surface
 *      the rebase prompt as a chat-thread message and apply nothing.
 *   3. On match: walk ops in order. Consecutive `add_node` ops collapse into
 *      one `addNodes` batch (single hash recompute); consecutive `connect`
 *      ops collapse into one `addEdges` batch. `update_node_config` and
 *      `remove_node` flush singly. Each group runs after a 100ms stagger.
 *   4. Cancellable via AbortSignal — the user clicking the canvas mid-apply
 *      drops every remaining op.
 *
 * NO modal — the rebase prompt is a chat-thread message, per
 * Memory/feedback_no_modals_except_confirm.md.
 */
import { logger } from '@/services/logger';
import {
  useWorkflowBuilderStore,
} from '@/features/orchestration/store/workflowBuilderStore';
import {
  isHardParseIssue,
  parseNodeConfig,
} from '@/features/orchestration/contracts/nodeConfig';
import type {
  WorkflowDefinitionEdge,
  WorkflowDefinitionNode,
} from '@/features/orchestration/types';

import {
  parseCanvasPatch,
  type CanvasPatch,
  type CanvasPatchAddNodeOp,
  type CanvasPatchConnectOp,
  type CanvasPatchOp,
  type CanvasPatchRemoveNodeOp,
  type CanvasPatchUpdateNodeConfigOp,
} from './canvasPatchSchema';

export interface ApplyCanvasPatchOptions {
  /** Inject a chat-thread message (the rebase prompt or a parse-error note).
   *  Wired by `useChatWidget.send` to its widget-store message API; tests
   *  pass a vi.fn() and assert on calls. */
  onChatMessage: (text: string) => void;
  /** Stagger between op-groups. Defaults to 100ms; tests pass `0`. */
  staggerMs?: number;
  /** AbortSignal to drop remaining ops mid-apply. Optional. */
  signal?: AbortSignal;
}

export type ApplyCanvasPatchResult =
  | { kind: 'applied'; opsApplied: number }
  | { kind: 'parse_error'; reason: string }
  | { kind: 'hash_mismatch' }
  | { kind: 'workflow_mismatch' }
  | { kind: 'version_mismatch' }
  | { kind: 'config_invalid'; nodeId: string; opKind: 'add_node' | 'update_node_config' }
  | { kind: 'aborted'; opsApplied: number };

const REBASE_PROMPT_TEXT =
  'The canvas changed while I was working — your changes are preserved. ' +
  'Want me to redo on the current state? Reply "yes, redo" to re-apply, or ignore to discard.';

/**
 * Phase 3 — module-level pending-rebase state. Set on hash-mismatch
 * with the patch's rationale; consumed by the chat widget's `send()`
 * when the user replies with a redo trigger. The rationale is carried
 * verbatim into the synthetic prompt the LLM receives.
 */
let pendingRebase: { rationale: string } | null = null;

const REDO_TRIGGERS = new Set(['yes, redo', 'yes redo', 'redo']);

function buildRebaseSynthetic(rationale: string): string {
  return (
    'Canvas state changed since my last patch. Re-read current state ' +
    `and re-apply the previous intent: ${rationale}`
  );
}

/**
 * Phase 3 — called by `useChatWidget.send` before dispatching a turn.
 * Returns the synthetic rebase prompt (carrying the cached rationale)
 * when:
 *   - a hash-mismatch is currently pending, AND
 *   - the user's text matches one of REDO_TRIGGERS (case-insensitive).
 *
 * Any other input clears the pending state — the implicit "discard"
 * path. Either way, after this call returns, the pending flag is gone
 * so the next mismatch starts fresh.
 *
 * Returns `null` when no rewrite should happen. Caller continues to
 * send the user's original text on the wire.
 */
export function consumeRebaseRedo(userText: string): string | null {
  if (pendingRebase === null) return null;
  const trimmed = userText.trim().toLowerCase();
  const rationale = pendingRebase.rationale;
  pendingRebase = null;
  if (REDO_TRIGGERS.has(trimmed)) {
    return buildRebaseSynthetic(rationale);
  }
  return null;
}

/**
 * Test-only helper — clears the pending-rebase state. Production code
 * never needs this; module-level state is intentional so the redo flow
 * can survive across re-renders.
 */
export function _resetRebaseStateForTests(): void {
  pendingRebase = null;
}

/** Pure helper — group consecutive same-kind ops so we can hand `add_node`
 *  runs to `addNodes(...)` and `connect` runs to `addEdges(...)` for a
 *  single hash recompute per group. Update / remove ops do not benefit
 *  from batching and pass through one-at-a-time. */
function groupOps(ops: readonly CanvasPatchOp[]): Array<
  | { kind: 'add_node_batch'; ops: CanvasPatchAddNodeOp[] }
  | { kind: 'connect_batch'; ops: CanvasPatchConnectOp[] }
  | { kind: 'update'; op: CanvasPatchUpdateNodeConfigOp }
  | { kind: 'remove'; op: CanvasPatchRemoveNodeOp }
> {
  const groups: ReturnType<typeof groupOps> = [];
  for (const op of ops) {
    if (op.op === 'add_node') {
      const last = groups[groups.length - 1];
      if (last && last.kind === 'add_node_batch') {
        last.ops.push(op);
      } else {
        groups.push({ kind: 'add_node_batch', ops: [op] });
      }
    } else if (op.op === 'connect') {
      const last = groups[groups.length - 1];
      if (last && last.kind === 'connect_batch') {
        last.ops.push(op);
      } else {
        groups.push({ kind: 'connect_batch', ops: [op] });
      }
    } else if (op.op === 'update_node_config') {
      groups.push({ kind: 'update', op });
    } else {
      groups.push({ kind: 'remove', op });
    }
  }
  return groups;
}

function nodeFromAddOp(op: CanvasPatchAddNodeOp): WorkflowDefinitionNode {
  return {
    id: op.node_id,
    type: op.payload.node_type,
    position: op.payload.position ?? { x: 0, y: 0 },
    data: {},
    config: op.payload.config as Record<string, unknown>,
  };
}

function edgeFromConnectOp(op: CanvasPatchConnectOp): WorkflowDefinitionEdge {
  return {
    id: op.payload.edge_id,
    source: op.payload.source_node_id,
    target: op.payload.target_node_id,
    output_id: op.payload.output_id,
  };
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  if (ms <= 0) return Promise.resolve();
  return new Promise((resolve) => {
    const id = window.setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      window.clearTimeout(id);
      resolve();
    };
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

/** Apply a patch against the live builder store. See file-level doc for
 *  the full behaviour spec. */
export async function applyCanvasPatch(
  raw: unknown,
  options: ApplyCanvasPatchOptions,
): Promise<ApplyCanvasPatchResult> {
  const parsed = parseCanvasPatch(raw);
  if (!parsed.ok) {
    logger.warn('orchestration.canvasPatchApplier.parse_failed', {
      issues: parsed.error.issues.slice(0, 3),
    });
    options.onChatMessage(
      "I drafted a canvas patch but it didn't match the expected shape — nothing was applied.",
    );
    return { kind: 'parse_error', reason: parsed.error.message };
  }

  const patch: CanvasPatch = parsed.data;
  const storeSnapshot = useWorkflowBuilderStore.getState();

  // Section 6 guard 1: workflow_id must match the live builder. A patch
  // emitted against workflow A applied while the operator is editing
  // workflow B would silently corrupt B's canvas.
  if (storeSnapshot.workflowId && patch.workflow_id !== storeSnapshot.workflowId) {
    logger.warn('orchestration.canvasPatchApplier.workflow_mismatch', {
      patch: patch.workflow_id,
      store: storeSnapshot.workflowId,
    });
    options.onChatMessage(
      "I drafted a patch for a different workflow — nothing was applied. " +
        'Reopen the canvas you intend to edit and ask again.',
    );
    return { kind: 'workflow_mismatch' };
  }

  // Section 6 guard 2: version_id compatibility. Both sides may be null
  // (a brand-new workflow with no draft yet). When both are present they
  // must agree; otherwise the patch was authored against a stale version
  // and applying it would race with whoever published in between.
  if (
    patch.version_id !== null &&
    storeSnapshot.versionId !== null &&
    patch.version_id !== storeSnapshot.versionId
  ) {
    logger.warn('orchestration.canvasPatchApplier.version_mismatch', {
      patch: patch.version_id,
      store: storeSnapshot.versionId,
    });
    options.onChatMessage(
      "The canvas was published or rebased since I drafted this patch — " +
        'nothing was applied. Re-ask and I will rebuild against the current version.',
    );
    return { kind: 'version_mismatch' };
  }

  const currentHash = storeSnapshot.currentDataHash;
  if (patch.base_data_hash !== currentHash) {
    logger.info('orchestration.canvasPatchApplier.hash_mismatch', {
      base: patch.base_data_hash,
      current: currentHash,
    });
    pendingRebase = { rationale: patch.rationale };
    options.onChatMessage(REBASE_PROMPT_TEXT);
    return { kind: 'hash_mismatch' };
  }
  // Apply path — any prior pending-rebase is now resolved.
  pendingRebase = null;

  // Section 6 guard 3: re-validate every add_node / update_node_config
  // op through the same draft parser the store uses. Backend canonical
  // validation runs at apply_patch time, but the SSE event could be
  // tampered, replayed, or hit a contract drift the backend already
  // forgave. Frontend revalidation closes the loop so a bad config
  // never lands in the store. Soft issues (missing required fields) are
  // tolerated; hard issues (fabricated keys, wrong types) abort apply.
  const baseNodesById = new Map<string, WorkflowDefinitionNode>(
    storeSnapshot.nodes.map((n) => [n.id, n]),
  );
  for (const op of patch.ops) {
    if (op.op === 'add_node') {
      const result = parseNodeConfig(op.payload.node_type, op.payload.config, {
        mode: 'draft',
      });
      const hard = !result.ok && result.issues.some(isHardParseIssue);
      if (hard) {
        logger.warn('orchestration.canvasPatchApplier.config_invalid_add_node', {
          nodeId: op.node_id,
          nodeType: op.payload.node_type,
          issues: result.issues.slice(0, 3),
        });
        options.onChatMessage(
          `I drafted a patch but op for ${op.node_id} (${op.payload.node_type}) ` +
            'has a schema issue — nothing was applied.',
        );
        return { kind: 'config_invalid', nodeId: op.node_id, opKind: 'add_node' };
      }
    } else if (op.op === 'update_node_config') {
      const target = baseNodesById.get(op.node_id);
      if (!target) continue; // applier raises later — the backend already gates this
      const merged = {
        ...(target.config as Record<string, unknown>),
        ...(op.payload.config_patch as Record<string, unknown>),
      };
      const result = parseNodeConfig(target.type, merged, { mode: 'draft' });
      const hard = !result.ok && result.issues.some(isHardParseIssue);
      if (hard) {
        logger.warn('orchestration.canvasPatchApplier.config_invalid_update', {
          nodeId: op.node_id,
          nodeType: target.type,
          issues: result.issues.slice(0, 3),
        });
        options.onChatMessage(
          `I drafted a patch but op for ${op.node_id} (${target.type}) ` +
            'has a schema issue — nothing was applied.',
        );
        return {
          kind: 'config_invalid',
          nodeId: op.node_id,
          opKind: 'update_node_config',
        };
      }
    }
  }

  const stagger = options.staggerMs ?? 100;
  const signal = options.signal;
  const groups = groupOps(patch.ops);
  const store = useWorkflowBuilderStore.getState();

  let opsApplied = 0;
  let firstGroup = true;
  for (const group of groups) {
    if (signal?.aborted) {
      return { kind: 'aborted', opsApplied };
    }
    if (!firstGroup) {
      await delay(stagger, signal);
      if (signal?.aborted) {
        return { kind: 'aborted', opsApplied };
      }
    }
    firstGroup = false;

    if (group.kind === 'add_node_batch') {
      store.addNodes(group.ops.map(nodeFromAddOp));
      opsApplied += group.ops.length;
    } else if (group.kind === 'connect_batch') {
      store.addEdges(group.ops.map(edgeFromConnectOp));
      opsApplied += group.ops.length;
    } else if (group.kind === 'update') {
      const patchObj = group.op.payload.config_patch as Record<string, unknown>;
      const existing = useWorkflowBuilderStore
        .getState()
        .nodes.find((n) => n.id === group.op.node_id);
      if (existing) {
        store.updateNodeConfig(group.op.node_id, {
          ...existing.config,
          ...patchObj,
        });
      }
      opsApplied += 1;
    } else {
      store.removeNode(group.op.node_id);
      opsApplied += 1;
    }
  }

  return { kind: 'applied', opsApplied };
}
