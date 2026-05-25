import type {
  UpstreamField,
  UpstreamUnresolved,
} from '@/services/api/orchestration';
import type {
  WorkflowDefinitionEdge,
  WorkflowDefinitionNode,
} from '@/features/orchestration/types';
import type { VariableInfo } from '@/types';

export interface UpstreamSubgraph {
  nodes: WorkflowDefinitionNode[];
  edges: WorkflowDefinitionEdge[];
}

/** Node ids reachable upstream of `targetNodeId` via incoming edges. */
function collectAncestors(
  targetNodeId: string,
  edges: readonly WorkflowDefinitionEdge[],
): Set<string> {
  const incoming = new Map<string, string[]>();
  for (const e of edges) {
    if (!incoming.has(e.target)) incoming.set(e.target, []);
    incoming.get(e.target)!.push(e.source);
  }
  const seen = new Set<string>();
  const stack = [...(incoming.get(targetNodeId) ?? [])];
  while (stack.length > 0) {
    const current = stack.pop()!;
    if (seen.has(current)) continue;
    seen.add(current);
    for (const parent of incoming.get(current) ?? []) {
      if (!seen.has(parent)) stack.push(parent);
    }
  }
  return seen;
}

/** The minimal upstream slice the resolver needs: ancestor nodes plus the
 *  edges wiring them into `targetNodeId`. The target node itself is excluded
 *  so editing its own config never changes the query key (no needless refetch).
 *  Used for both the request body and the TanStack Query key. */
export function extractUpstreamSubgraph(
  targetNodeId: string,
  nodes: readonly WorkflowDefinitionNode[],
  edges: readonly WorkflowDefinitionEdge[],
): UpstreamSubgraph {
  const ancestors = collectAncestors(targetNodeId, edges);
  const relevant = new Set([...ancestors, targetNodeId]);
  return {
    nodes: nodes.filter((n) => ancestors.has(n.id)),
    edges: edges.filter((e) => relevant.has(e.source) && relevant.has(e.target)),
  };
}

const TEMPLATE_VAR = /\{\{\s*([\w.]+)\s*\}\}/g;

/** Unique `{{var}}` names referenced in `text`, trimmed; dotted paths kept. */
export function extractTemplateVariables(text: string): string[] {
  const seen = new Set<string>();
  for (const match of text.matchAll(TEMPLATE_VAR)) seen.add(match[1]);
  return [...seen];
}

/** Variables referenced in the prompt that no resolved field provides. Lint is
 *  OFF when the resolver returned no fields — an event upstream contributes only
 *  `unresolved`, so we must not flag every `{{var}}` as unknown. */
export function lintUnknownVariables(
  prompt: string,
  fields: readonly UpstreamField[],
): string[] {
  if (fields.length === 0) return [];
  const known = new Set(fields.map((f) => f.path));
  return extractTemplateVariables(prompt).filter((v) => !known.has(v));
}

const normalizeVarName = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '');

/** The known field path that an unknown `{{var}}` most likely meant — matched
 *  ignoring case and punctuation (e.g. `lastmessage` → `last_message`). Powers
 *  the "did you mean" lint hint. Null when nothing matches. */
export function suggestKnownVariable(
  unknown: string,
  fields: readonly UpstreamField[],
): string | null {
  const target = normalizeVarName(unknown);
  return fields.find((f) => normalizeVarName(f.path) === target)?.path ?? null;
}

export type ParentLockStatus = 'no-upstream' | 'unresolved-only' | 'resolved';

/** Soft parent-lock state. An event upstream is `unresolved-only`
 *  (valid-but-unresolved) — never reported as "no upstream". */
export function parentLockStatus(
  fields: readonly UpstreamField[],
  unresolved: readonly UpstreamUnresolved[],
): ParentLockStatus {
  if (fields.length > 0) return 'resolved';
  if (unresolved.length > 0) return 'unresolved-only';
  return 'no-upstream';
}

/** True when "Save results as" would shadow an existing upstream top-level key,
 *  making downstream `{namespace}.field` references ambiguous. */
export function saveAsCollides(
  namespace: string | undefined,
  fields: readonly UpstreamField[],
): boolean {
  if (!namespace) return false;
  return fields.some((f) => f.path.split('.')[0] === namespace);
}

const SOURCE_GROUP_LABELS: Record<string, string> = {
  cohort: 'Cohort fields',
  dataset: 'Dataset columns',
  static: 'Record fields',
  step: 'Earlier steps',
};

export function sourceGroupLabel(source: string): string {
  return SOURCE_GROUP_LABELS[source] ?? 'Variables';
}

/** Map a resolved field to the VariablePickerPopover `VariableInfo` shape so
 *  the inline prompt picker reuses the existing component (static-only). */
export function toVariableInfo(field: UpstreamField): VariableInfo {
  return {
    key: field.path,
    displayName: field.path,
    description: sourceGroupLabel(field.source),
    category: sourceGroupLabel(field.source),
    valueType: field.type,
    requiresAudio: false,
    requiresEvalOutput: false,
    sourceTypes: null,
    example: field.sampleValue == null ? '' : String(field.sampleValue),
  };
}
