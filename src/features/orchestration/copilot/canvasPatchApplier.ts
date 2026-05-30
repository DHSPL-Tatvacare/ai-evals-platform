/**
 * Pure canvas-patch applier — translates a validated `CanvasPatch` off the
 * chat stream into `workflowBuilderStore` mutations and returns an enriched
 * result the caller can narrate, gate, or undo.
 *
 * Behaviour:
 *   1. Validate via Zod. Drift returns `parse_error`; never throws.
 *   2. Guards: workflow_id / version_id / base_data_hash must match the live
 *      builder. A mismatch returns the discriminated result and applies
 *      nothing (the chat widget owns any rebase prompt — the applier holds no
 *      module state).
 *   3. Re-validate every add_node / update_node_config config through the
 *      draft parser before applying; a hard issue returns `config_invalid`.
 *   4. Walk ops in order. Consecutive `add_node` ops collapse into one
 *      `addNodes` batch (single hash recompute); consecutive `connect` ops
 *      collapse into one `addEdges` batch. `update_node_config` and
 *      `remove_node` flush singly. Each group runs after a `staggerMs` delay.
 *   5. Cancellable via AbortSignal — the user clicking the canvas mid-apply
 *      drops every remaining op.
 *   6. Capture the INVERSE op per applied op (pre-apply) so the caller can
 *      undo the whole patch.
 */
import { logger } from '@/services/logger';
import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import {
  isHardParseIssue,
  parseNodeConfig,
} from '@/features/orchestration/contracts/nodeConfig';
import type {
  NodeTypeDescriptor,
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
  /** Stagger between op-groups. Defaults to 100ms; tests pass `0`. */
  staggerMs?: number;
  /** AbortSignal to drop remaining ops mid-apply. Optional. */
  signal?: AbortSignal;
}

/** One step that undoes a single applied op. The caller replays these
 *  against the store (in reverse) to revert a whole patch. */
export type CanvasPatchInverseOp =
  | { kind: 'remove_node'; nodeId: string }
  | { kind: 'remove_edge'; edgeId: string }
  | { kind: 'update_node_config'; nodeId: string; config: Record<string, unknown> }
  | {
      kind: 'add_node';
      node: WorkflowDefinitionNode;
      edges: WorkflowDefinitionEdge[];
    };

export interface ApplyCanvasPatchApplied {
  kind: 'applied';
  opsApplied: number;
  addedNodeIds: string[];
  editedNodeIds: string[];
  removedNodeIds: string[];
  connectEdgeIds: string[];
  rationale: string;
  inverse: CanvasPatchInverseOp[];
}

export type ApplyCanvasPatchResult =
  | ApplyCanvasPatchApplied
  | { kind: 'parse_error'; reason: string }
  | { kind: 'hash_mismatch'; rationale: string }
  | { kind: 'workflow_mismatch' }
  | { kind: 'version_mismatch' }
  | { kind: 'config_invalid'; nodeId: string; opKind: 'add_node' | 'update_node_config' }
  | { kind: 'aborted'; opsApplied: number };

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

/** Hydrate `data.{label, nodeType}` from the palette descriptor so the new
 *  node and the canvas card read the descriptor label — never a hardcoded
 *  string. Falls back to the node type when no descriptor is registered. */
function nodeFromAddOp(
  op: CanvasPatchAddNodeOp,
  catalog: readonly NodeTypeDescriptor[],
): WorkflowDefinitionNode {
  const desc = catalog.find((d) => d.nodeType === op.payload.node_type);
  return {
    id: op.node_id,
    type: op.payload.node_type,
    position: op.payload.position ?? { x: 0, y: 0 },
    data: {
      label: desc?.displayLabel ?? desc?.label ?? op.payload.node_type,
      nodeType: op.payload.node_type,
    },
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

/** Strip the FE-only `_parseIssues` annotation so a captured snapshot (used
 *  in a `remove_node` inverse) is a clean re-addable node. */
function cleanNode(node: WorkflowDefinitionNode): WorkflowDefinitionNode {
  if (!node._parseIssues) return node;
  const rest = { ...node };
  delete rest._parseIssues;
  return rest;
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

/** Apply a patch against the live builder store. See file-level doc for the
 *  full behaviour spec. Pure: returns the outcome; the caller decides what
 *  to narrate or undo. */
export async function applyCanvasPatch(
  raw: unknown,
  options: ApplyCanvasPatchOptions = {},
): Promise<ApplyCanvasPatchResult> {
  const parsed = parseCanvasPatch(raw);
  if (!parsed.ok) {
    logger.warn('orchestration.canvasPatchApplier.parse_failed', {
      issues: parsed.error.issues.slice(0, 3),
    });
    return { kind: 'parse_error', reason: parsed.error.message };
  }

  const patch: CanvasPatch = parsed.data;
  const storeSnapshot = useWorkflowBuilderStore.getState();

  // Guard 1: workflow_id must match the live builder. A patch emitted against
  // workflow A applied while the operator is editing workflow B would
  // silently corrupt B's canvas.
  if (storeSnapshot.workflowId && patch.workflow_id !== storeSnapshot.workflowId) {
    logger.warn('orchestration.canvasPatchApplier.workflow_mismatch', {
      patch: patch.workflow_id,
      store: storeSnapshot.workflowId,
    });
    return { kind: 'workflow_mismatch' };
  }

  // Guard 2: version_id compatibility. Both sides may be null (a brand-new
  // workflow with no draft yet). When both are present they must agree;
  // otherwise the patch was authored against a stale version and applying it
  // would race with whoever published in between.
  if (
    patch.version_id !== null &&
    storeSnapshot.versionId !== null &&
    patch.version_id !== storeSnapshot.versionId
  ) {
    logger.warn('orchestration.canvasPatchApplier.version_mismatch', {
      patch: patch.version_id,
      store: storeSnapshot.versionId,
    });
    return { kind: 'version_mismatch' };
  }

  const currentHash = storeSnapshot.currentDataHash;
  if (patch.base_data_hash !== currentHash) {
    logger.info('orchestration.canvasPatchApplier.hash_mismatch', {
      base: patch.base_data_hash,
      current: currentHash,
    });
    return { kind: 'hash_mismatch', rationale: patch.rationale };
  }

  // Guard 3: re-validate every add_node / update_node_config op through the
  // same draft parser the store uses. Backend canonical validation runs at
  // apply_patch time, but the SSE event could be tampered, replayed, or hit a
  // contract drift the backend already forgave. Frontend revalidation closes
  // the loop so a bad config never lands in the store. Soft issues (missing
  // required fields) are tolerated; hard issues (fabricated keys, wrong
  // types) abort apply.
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
  const catalog = storeSnapshot.paletteCatalog;
  const groups = groupOps(patch.ops);
  const store = useWorkflowBuilderStore.getState();

  const addedNodeIds: string[] = [];
  const editedNodeIds: string[] = [];
  const removedNodeIds: string[] = [];
  const connectEdgeIds: string[] = [];
  const inverse: CanvasPatchInverseOp[] = [];

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
      store.addNodes(group.ops.map((op) => nodeFromAddOp(op, catalog)));
      for (const op of group.ops) {
        addedNodeIds.push(op.node_id);
        inverse.push({ kind: 'remove_node', nodeId: op.node_id });
      }
      opsApplied += group.ops.length;
    } else if (group.kind === 'connect_batch') {
      store.addEdges(group.ops.map(edgeFromConnectOp));
      for (const op of group.ops) {
        connectEdgeIds.push(op.payload.edge_id);
        inverse.push({ kind: 'remove_edge', edgeId: op.payload.edge_id });
      }
      opsApplied += group.ops.length;
    } else if (group.kind === 'update') {
      const patchObj = group.op.payload.config_patch as Record<string, unknown>;
      const existing = useWorkflowBuilderStore
        .getState()
        .nodes.find((n) => n.id === group.op.node_id);
      if (existing) {
        inverse.push({
          kind: 'update_node_config',
          nodeId: group.op.node_id,
          config: { ...(existing.config as Record<string, unknown>) },
        });
        store.updateNodeConfig(group.op.node_id, {
          ...existing.config,
          ...patchObj,
        });
        editedNodeIds.push(group.op.node_id);
      }
      opsApplied += 1;
    } else {
      // Capture the node + its dependent edges BEFORE removal so the inverse
      // can re-add both.
      const state = useWorkflowBuilderStore.getState();
      const victim = state.nodes.find((n) => n.id === group.op.node_id);
      if (victim) {
        const dependentEdges = state.edges.filter(
          (e) => e.source === group.op.node_id || e.target === group.op.node_id,
        );
        inverse.push({
          kind: 'add_node',
          node: cleanNode(victim),
          edges: dependentEdges.map((e) => ({ ...e })),
        });
        removedNodeIds.push(group.op.node_id);
      }
      store.removeNode(group.op.node_id);
      opsApplied += 1;
    }
  }

  return {
    kind: 'applied',
    opsApplied,
    addedNodeIds,
    editedNodeIds,
    removedNodeIds,
    connectEdgeIds,
    rationale: patch.rationale,
    inverse,
  };
}
