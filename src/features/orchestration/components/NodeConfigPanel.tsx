import { useMemo } from 'react';
import { X } from 'lucide-react';

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
  const clearSelection = useWorkflowBuilderStore((s) => s.clearSelection);

  const hiddenFields = useMemo<ReadonlySet<string> | undefined>(() => {
    if (!node) return undefined;
    // Source-node ``next_node_id`` is auto-derived from the outgoing default
    // edge at save time; surfacing the manual field would let an author enter
    // a value that drifts away from the visual graph and silently fail to
    // publish.
    return isSourceNodeType(node.type) ? SOURCE_HIDDEN_FIELDS : undefined;
  }, [node]);

  const closeButton = (
    <button
      type="button"
      onClick={clearSelection}
      aria-label="Close inspector"
      className="rounded p-1 text-[var(--text-muted)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
    >
      <X className="h-3.5 w-3.5" />
    </button>
  );

  if (!node) {
    return (
      <div className="flex h-full w-80 items-center justify-center border-l border-[var(--border-subtle)] p-4 text-sm text-[var(--text-secondary)]">
        Select a node to edit its config.
      </div>
    );
  }
  const desc = palette.find((p) => p.nodeType === node.type);
  if (!desc) {
    return (
      <div className="flex h-full w-80 flex-col border-l border-[var(--border-subtle)] p-4 text-sm text-[var(--text-secondary)]">
        <div className="mb-2 flex items-start justify-between gap-2">
          <span>Unknown node type: {node.type}</span>
          {closeButton}
        </div>
      </div>
    );
  }
  return (
    <div className="flex h-full w-80 flex-col gap-3 overflow-y-auto border-l border-[var(--border-subtle)] p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-medium text-[var(--text-primary)]">
            {desc.label}
          </div>
          <div className="truncate text-xs text-[var(--text-secondary)]">
            {desc.nodeType}
          </div>
        </div>
        {closeButton}
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
        appId="inside-sales"
        connectionIdForVariables={
          typeof node.config.connection_id === 'string'
            ? node.config.connection_id
            : undefined
        }
      />
    </div>
  );
}
