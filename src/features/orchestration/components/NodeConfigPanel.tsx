import { useMemo } from 'react';

import {
  isSourceNodeType,
  useWorkflowBuilderStore,
} from '@/features/orchestration/store/workflowBuilderStore';
import { DynamicConfigForm, type JsonSchema } from './DynamicConfigForm';

const SOURCE_HIDDEN_FIELDS: ReadonlySet<string> = new Set(['next_node_id']);

export function NodeConfigPanel() {
  const selectedNodeId = useWorkflowBuilderStore((s) => s.selectedNodeId);
  const node = useWorkflowBuilderStore((s) =>
    s.nodes.find((n) => n.id === selectedNodeId) ?? null,
  );
  const palette = useWorkflowBuilderStore((s) => s.paletteCatalog);
  const updateConfig = useWorkflowBuilderStore((s) => s.updateNodeConfig);

  const hiddenFields = useMemo<ReadonlySet<string> | undefined>(() => {
    if (!node) return undefined;
    // Source-node ``next_node_id`` is auto-derived from the outgoing default
    // edge at save time; surfacing the manual field would let an author enter
    // a value that drifts away from the visual graph and silently fail to
    // publish.
    return isSourceNodeType(node.type) ? SOURCE_HIDDEN_FIELDS : undefined;
  }, [node]);

  if (!node) {
    return (
      <div className="flex h-full w-80 items-center justify-center border-l border-[var(--border-default)] p-4 text-sm text-[var(--text-secondary)]">
        Select a node to edit its config.
      </div>
    );
  }
  const desc = palette.find((p) => p.nodeType === node.type);
  if (!desc) {
    return (
      <div className="w-80 border-l border-[var(--border-default)] p-4 text-sm text-[var(--text-secondary)]">
        Unknown node type: {node.type}
      </div>
    );
  }
  return (
    <div className="flex h-full w-80 flex-col gap-3 overflow-y-auto border-l border-[var(--border-default)] p-4">
      <div>
        <div className="font-medium text-[var(--text-primary)]">{desc.label}</div>
        <div className="text-xs text-[var(--text-secondary)]">{desc.nodeType}</div>
      </div>
      {isSourceNodeType(node.type) && (
        <p className="rounded-[var(--radius-default)] bg-[var(--bg-tertiary)] p-2 text-xs text-[var(--text-secondary)]">
          Source nodes route to the next node via the visual edge — connect this
          node to the next node on the canvas instead of editing
          <code className="mx-1">next_node_id</code> by hand.
        </p>
      )}
      <DynamicConfigForm
        schema={desc.configSchema as unknown as JsonSchema}
        value={node.config}
        onChange={(next) => updateConfig(node.id, next)}
        hiddenFields={hiddenFields}
      />
    </div>
  );
}
