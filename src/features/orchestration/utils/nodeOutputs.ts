import type {
  NodeTypeDescriptor,
  WorkflowDefinitionNode,
} from '@/features/orchestration/types';

/** Derive the runtime output-handle ids for a node.
 *
 * Most nodes carry static handles from their palette descriptor
 * (`outputEdges`). `logic.split` / `logic.conditional` / `logic.wait` are
 * special: their handles are config-derived, so the canvas (and the store's
 * branch-delete cleanup) must recompute them per node config. The static
 * descriptor for split is empty and would otherwise collapse into a single
 * `default` handle. */
export function deriveOutputEdges(
  node: WorkflowDefinitionNode,
  desc: NodeTypeDescriptor | undefined,
): string[] {
  if (node.type === 'logic.split') {
    const branches = (node.config?.branches as Array<{ id?: string }> | undefined) ?? [];
    const ids = branches
      .map((b) => (typeof b?.id === 'string' ? b.id.trim() : ''))
      .filter((s) => s.length > 0);
    // Percentage holdout routes its share to a reserved ``control`` edge.
    const scfg = (node.config ?? {}) as { mode?: string; holdout_percent?: number | null };
    if (scfg.mode === 'percentage' && (scfg.holdout_percent ?? 0) > 0 && !ids.includes('control')) {
      ids.push('control');
    }
    if (ids.length > 0) return ids;
  }
  if (node.type === 'logic.conditional') {
    // Branch ids are the routing keys; unmatched contacts always fall to
    // ``default``, so the canvas shows one handle per branch plus default.
    const branches = (node.config?.branches as Array<{ id?: string }> | undefined) ?? [];
    const ids = branches
      .map((b) => (typeof b?.id === 'string' ? b.id.trim() : ''))
      .filter((s) => s.length > 0);
    return [...ids, 'default'];
  }
  if (node.type === 'logic.wait') {
    // Only the outputs that match the configured wait mode are valid — the
    // descriptor lists all three for the validator's benefit, but the canvas
    // renders only the ones the operator can actually wire.
    const cfg = (node.config ?? {}) as { mode?: string };
    if (cfg.mode === 'duration' || cfg.mode === 'until_datetime') return ['wakeup'];
    if (cfg.mode === 'event') return ['event'];
    if (cfg.mode === 'event_or_timeout') return ['event', 'timeout'];
  }
  const fromDesc = (desc?.outputEdges ?? []).map((oe) => oe.id);
  return fromDesc.length > 0 ? fromDesc : ['default'];
}

/** Map a node's outgoing handle ids to human-readable labels for the canvas
 *  card (e.g. ``success`` -> ``Success``). Split / conditional nodes use the
 *  branch's editable label, mirroring the ``id -> label`` shape declared on
 *  the descriptor for static outputs. */
export function deriveOutputEdgeLabels(
  node: WorkflowDefinitionNode,
  desc: NodeTypeDescriptor | undefined,
): Record<string, string> {
  const out: Record<string, string> = {};
  if (node.type === 'logic.split' || node.type === 'logic.conditional') {
    const branches =
      (node.config?.branches as Array<{ id?: string; label?: string }> | undefined) ?? [];
    for (const b of branches) {
      if (typeof b?.id === 'string' && b.id.trim().length > 0) {
        out[b.id] = typeof b.label === 'string' && b.label.trim().length > 0 ? b.label : b.id;
      }
    }
    if (node.type === 'logic.conditional') out.default = 'Default';
    const scfg = (node.config ?? {}) as { mode?: string; holdout_percent?: number | null };
    if (node.type === 'logic.split' && scfg.mode === 'percentage' && (scfg.holdout_percent ?? 0) > 0) {
      out.control = 'Control';
    }
    return out;
  }
  for (const oe of desc?.outputEdges ?? []) {
    out[oe.id] = oe.label ?? oe.id;
  }
  return out;
}

/** Whether a node's output handle accepts more than one outgoing edge
 *  (fan-out). Static handles declare this via ``cardinality: 'many'``;
 *  node-level ``graphRules.allowsMultipleOutgoingPerOutput`` is the coarse
 *  fallback for config-derived handles (split / conditional) that have no
 *  per-handle descriptor. Default is single-binding — the safe choice that
 *  prevents silent duplicate routing. */
export function outputAllowsFanOut(
  outputId: string,
  desc: NodeTypeDescriptor | undefined,
): boolean {
  const handle = desc?.outputEdges?.find((oe) => oe.id === outputId);
  if (handle) return handle.cardinality === 'many';
  return Boolean(desc?.graphRules?.allowsMultipleOutgoingPerOutput);
}
