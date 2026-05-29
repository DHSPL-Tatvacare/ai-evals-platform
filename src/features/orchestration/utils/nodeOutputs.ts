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

type WaitConfig = {
  mode?: string;
  duration_value?: number;
  duration_unit?: string;
  duration_hours?: number;
  until_datetime?: string;
  event_name?: string;
  timeout_hours?: number;
};

/** Singular/plural-aware duration phrase, e.g. ``15 minutes`` / ``1 hour``. */
function waitDurationPhrase(cfg: WaitConfig): string {
  const value = cfg.duration_value ?? cfg.duration_hours;
  const unit = cfg.duration_unit ?? 'hours';
  if (value == null) return 'a set time';
  const singular = unit.replace(/s$/, '');
  return `${value} ${value === 1 ? singular : `${singular}s`}`;
}

/** Render an ISO datetime as ``YYYY-MM-DD HH:mm UTC`` for the canvas. Falls
 *  back to the raw string when it isn't a parseable timestamp. */
function waitUntilPhrase(iso: string | undefined): string {
  if (!iso) return 'a date & time';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ` +
    `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`
  );
}

/** Human body line summarizing what a ``logic.wait`` node waits for, mirroring
 *  the run canvas's ``Cohort: N`` body pattern. Reads only the persisted config
 *  (no contract change). */
export function deriveWaitBodySummary(node: WorkflowDefinitionNode): string | undefined {
  if (node.type !== 'logic.wait') return undefined;
  const cfg = (node.config ?? {}) as WaitConfig;
  const mode = cfg.mode ?? (cfg.until_datetime ? 'until_datetime' : 'duration');
  if (mode === 'until_datetime') return `Wait until ${waitUntilPhrase(cfg.until_datetime)}`;
  if (mode === 'event') return `Wait for: ${cfg.event_name || 'an event'}`;
  if (mode === 'event_or_timeout') {
    const evt = cfg.event_name || 'an event';
    const timeout = cfg.timeout_hours != null ? ` · timeout ${cfg.timeout_hours}h` : '';
    return `Wait for ${evt}${timeout}`;
  }
  return `Wait ${waitDurationPhrase(cfg)}`;
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
  if (node.type === 'logic.wait') {
    // Mode-accurate edge labels so a wait reads correctly at a glance and
    // aligns with the handles ``deriveOutputEdges`` renders for the mode.
    const cfg = (node.config ?? {}) as WaitConfig;
    const mode = cfg.mode ?? (cfg.until_datetime ? 'until_datetime' : 'duration');
    if (mode === 'until_datetime') return { wakeup: `Until ${waitUntilPhrase(cfg.until_datetime)}` };
    if (mode === 'event') return { event: `On ${cfg.event_name || 'event'}` };
    if (mode === 'event_or_timeout') {
      return {
        event: `On ${cfg.event_name || 'event'}`,
        timeout: cfg.timeout_hours != null ? `Timeout ${cfg.timeout_hours}h` : 'Timeout',
      };
    }
    return { wakeup: `After ${waitDurationPhrase(cfg)}` };
  }
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
