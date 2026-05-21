import type {
  WorkflowDefinitionEdge,
  WorkflowDefinitionNode,
} from '@/features/orchestration/types';

/** Payload keys a dispatch node writes back onto a recipient's payload,
 *  reachable downstream as `steps.<nodeId>.<key>`. No backend registry of
 *  emitted keys exists yet, so the known messaging/voice keys live here. */
const EMITTED_KEYS_BY_NODE_TYPE: Record<string, string[]> = {
  'messaging.send_whatsapp_template': ['wa_button_id', 'wa_reply_text'],
  'voice.place_call': ['voice_outcome'],
};

function payloadFieldsFromConfig(config: Record<string, unknown>): string[] {
  const raw = config.payload_fields;
  if (!Array.isArray(raw)) return [];
  return raw.filter((f): f is string => typeof f === 'string');
}

/** Compute the payload keys available at `nodeId` by walking the graph
 *  upstream. Collects each upstream source's declared `payload_fields` plus
 *  the `steps.<nodeId>.<key>` keys emitted by upstream dispatch nodes.
 *  Sorted and de-duplicated. Free-text remains the fallback when this is
 *  empty (the field input degrades to a plain text box). */
export function upstreamPayloadFields(
  nodeId: string,
  nodes: readonly WorkflowDefinitionNode[],
  edges: readonly WorkflowDefinitionEdge[],
): string[] {
  const nodeById = new Map(nodes.map((n) => [n.id, n]));
  const incoming = new Map<string, string[]>();
  for (const edge of edges) {
    if (!incoming.has(edge.target)) incoming.set(edge.target, []);
    incoming.get(edge.target)!.push(edge.source);
  }

  const fields = new Set<string>();
  const visited = new Set<string>();
  const stack = [...(incoming.get(nodeId) ?? [])];
  while (stack.length > 0) {
    const current = stack.pop()!;
    if (visited.has(current)) continue;
    visited.add(current);
    const node = nodeById.get(current);
    if (node) {
      for (const f of payloadFieldsFromConfig(node.config)) fields.add(f);
      for (const key of EMITTED_KEYS_BY_NODE_TYPE[node.type] ?? []) {
        fields.add(`steps.${node.id}.${key}`);
      }
    }
    for (const parent of incoming.get(current) ?? []) {
      if (!visited.has(parent)) stack.push(parent);
    }
  }
  return Array.from(fields).sort();
}
