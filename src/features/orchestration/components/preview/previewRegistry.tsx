import { TemplateMessagePreview } from './TemplateMessagePreview';

/** Config shape a preview reads — the inspector's node config, loosely typed. */
type NodeConfig = Record<string, unknown>;

/** A preview renders to the right of the inspector form for a given node type.
 *  Voice (agent-prompt preview) registers here later — keyed by node type so
 *  the inspector shell stays channel-agnostic. */
export type NodePreview = (config: NodeConfig) => React.ReactNode;

function asString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

function asVariableMappings(value: unknown) {
  return Array.isArray(value)
    ? (value as Parameters<typeof TemplateMessagePreview>[0]['variableMappings'])
    : [];
}

const PREVIEW_BY_NODE_TYPE: Record<string, NodePreview> = {
  'messaging.send_whatsapp_template': (config) => (
    <TemplateMessagePreview
      connectionId={asString(config.connection_id)}
      templateName={asString(config.template_name)}
      variableMappings={asVariableMappings(config.variable_mappings)}
    />
  ),
};

export function getPreviewForNode(nodeType: string): NodePreview | null {
  return PREVIEW_BY_NODE_TYPE[nodeType] ?? null;
}
