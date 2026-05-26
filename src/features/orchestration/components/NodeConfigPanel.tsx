import { useMemo } from 'react';
import { X } from 'lucide-react';

import { cn } from '@/utils/cn';
import { useCurrentAppId } from '@/hooks';
import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import type {
  ConditionalBranch,
  MergePolicy,
  PayloadPolicy,
  PredicateAst,
  SplitBranch,
  SplitMode,
  WorkflowType,
} from '@/features/orchestration/types';

import { DynamicConfigForm, type JsonSchema } from './DynamicConfigForm';
import { FieldSpotlightProvider } from './inspector/FieldSpotlightProvider';
import { InspectorSection } from './inspector/InspectorPrimitives';
import { useResizableInspectorWidth } from './inspector/useResizableInspectorWidth';
import { getPreviewForNode } from './preview/previewRegistry';
import { ConditionalBranchesEditor } from './editors/ConditionalBranchesEditor';
import { DatasetPicker } from './editors/DatasetPicker';
import { EventTriggerInspector } from './EventTriggerInspector';
import { LlmExtractInspector } from './LlmExtractInspector';
import { MergePolicyEditor } from './editors/MergePolicyEditor';
import { RuleSetBuilder } from './editors/RuleSetBuilder';
import { SourceCohortPicker } from './editors/SourceCohortPicker';
import { SplitBranchEditor } from './editors/SplitBranchEditor';
import { useResolveUpstreamVariables } from '@/features/orchestration/queries/upstreamVariables';
import { WaitConditionEditor } from './editors/WaitConditionEditor';
import { WebhookOutEditor } from './editors/WebhookOutEditor';

export function NodeConfigPanel() {
  const appId = useCurrentAppId();
  const selectedNodeId = useWorkflowBuilderStore((s) => s.selectedNodeId);
  const node = useWorkflowBuilderStore((s) =>
    s.nodes.find((n) => n.id === selectedNodeId) ?? null,
  );
  const palette = useWorkflowBuilderStore((s) => s.paletteCatalog);
  const nodes = useWorkflowBuilderStore((s) => s.nodes);
  const edges = useWorkflowBuilderStore((s) => s.edges);
  const workflowType = useWorkflowBuilderStore((s) => s.workflowType);
  const updateConfig = useWorkflowBuilderStore((s) => s.updateNodeConfig);
  const clearSelection = useWorkflowBuilderStore((s) => s.clearSelection);
  // Phase-14 follow-up — view mode renders the same inspector body
  // wrapped in a disabled fieldset. Browser-native disabling propagates
  // to every form input and button inside, so we don't have to thread a
  // `readOnly` prop through every specialised editor.
  const viewMode = useWorkflowBuilderStore((s) => s.viewMode);
  const setViewMode = useWorkflowBuilderStore((s) => s.setViewMode);
  const readOnly = viewMode === 'view';

  // Resizable 2-pane shell: width + drag handlers live here so any node type
  // with a registered preview docks into the same wide, resizable inspector.
  const resize = useResizableInspectorWidth();

  // Descriptor lookup must come before any conditional rendering so the
  // hooks below see a stable input identity regardless of node selection.
  const desc = useMemo(
    () => palette.find((p) => p.nodeType === node?.type) ?? null,
    [palette, node?.type],
  );

  // Payload keys reachable at this node, resolved upstream by the backend —
  // feeds the field dropdown for predicate-driven editors. Empty list (or
  // in-flight) degrades to free-text.
  const { data: upstreamData } = useResolveUpstreamVariables({
    appId,
    workflowType,
    nodes,
    edges,
    targetNodeId: node?.id,
  });
  const upstreamFields = useMemo(
    () => (upstreamData?.fields ?? []).map((f) => f.path),
    [upstreamData],
  );

  const editorHints = desc?.editorHints;
  const hiddenFields = useMemo<ReadonlySet<string> | undefined>(() => {
    const declared = (editorHints?.hiddenFields as string[] | undefined) ?? [];
    if (declared.length === 0) return undefined;
    return new Set(declared);
  }, [editorHints]);

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
      <div className="flex h-full w-[var(--inspector-width-node)] items-center justify-center border-l border-[var(--border-subtle)] p-4 text-sm text-[var(--text-secondary)]">
        Select a node to edit its config.
      </div>
    );
  }
  if (!desc) {
    return (
      <div className="flex h-full w-[var(--inspector-width-node)] flex-col border-l border-[var(--border-subtle)] p-4 text-sm text-[var(--text-secondary)]">
        <div className="mb-2 flex items-start justify-between gap-2">
          <span>Unknown node type: {node.type}</span>
          {closeButton}
        </div>
      </div>
    );
  }

  // Descriptor-driven editor dispatch. A specialised editor is chosen via
  // `descriptor.editorHints.preferredEditor`; nodes without a hint render
  // through `DynamicConfigForm`.
  const preferredEditor = desc.editorHints?.preferredEditor as
    | string
    | undefined;

  const _wfType = (workflowType ?? 'crm') as WorkflowType;
  const config = node.config as Record<string, unknown>;

  // Common helper used by every specialised editor: shallow-merge a config
  // patch and persist via the store. Specialised editors hand back a full
  // canonical sub-object for their slice so we don't have to thread a
  // separate `patch` shape.
  const setConfig = (next: Record<string, unknown>) => updateConfig(node.id, next);

  // The AI agent inspector owns its own wide 3-pane shell (header, panes,
  // drag-resize), so it replaces the standard fixed-width panel entirely.
  if (node.type === 'llm.extract') {
    return (
      <LlmExtractInspector
        value={config}
        onChange={(next) => setConfig({ ...config, ...next })}
        workflowType={_wfType}
        displayLabel={desc.displayLabel ?? desc.label}
        nodeType={desc.nodeType}
        onClose={clearSelection}
        readOnly={readOnly}
      />
    );
  }

  const fieldOptions = upstreamFields.length > 0 ? upstreamFields : undefined;

  let body: React.ReactNode;

  switch (preferredEditor) {
    case 'SourceCohortPicker': {
      body = (
        <SourceCohortPicker
          value={config}
          onChange={(next) => setConfig({ ...config, ...next })}
        />
      );
      break;
    }
    case 'DatasetPicker': {
      body = (
        <DatasetPicker
          value={config}
          onChange={(next) => setConfig({ ...config, ...next })}
        />
      );
      break;
    }
    case 'PredicateBuilder': {
      // `logic.wait` embeds a predicate builder for event_match; the
      // eligibility filter uses the shared RuleSetBuilder on its single
      // predicate. (`logic.conditional` routes to ConditionalBranchesEditor.)
      const isWait = node.type === 'logic.wait';
      body = isWait ? (
        <WaitConditionEditor
          value={config as Parameters<typeof WaitConditionEditor>[0]['value']}
          onChange={(next) => setConfig({ ...config, ...next })}
        />
      ) : (
        <RuleSetBuilder
          value={config.predicate as PredicateAst | undefined}
          onChange={(next) => setConfig({ ...config, predicate: next })}
          fieldOptions={fieldOptions}
        />
      );
      break;
    }
    case 'ConditionalBranchesEditor': {
      body = (
        <ConditionalBranchesEditor
          value={config as { branches?: ConditionalBranch[] }}
          onChange={(next) => setConfig({ ...config, ...next })}
          fieldOptions={fieldOptions}
        />
      );
      break;
    }
    case 'SplitBranchEditor': {
      body = (
        <SplitBranchEditor
          value={config as {
            mode?: SplitMode;
            field?: string;
            branches?: SplitBranch[];
            default_branch_id?: string;
            drop_unmatched?: boolean;
          }}
          onChange={(next) => setConfig({ ...config, ...next })}
          fieldOptions={fieldOptions}
        />
      );
      break;
    }
    case 'WaitConditionEditor': {
      body = (
        <WaitConditionEditor
          value={config as Parameters<typeof WaitConditionEditor>[0]['value']}
          onChange={(next) => setConfig({ ...config, ...next })}
        />
      );
      break;
    }
    case 'MergePolicyEditor': {
      body = (
        <MergePolicyEditor
          value={
            config as { merge_policy?: MergePolicy; payload_policy?: PayloadPolicy }
          }
          onChange={(next) => setConfig({ ...config, ...next })}
        />
      );
      break;
    }
    case 'StructuredRequestBodyEditor': {
      body = (
        <WebhookOutEditor
          value={config}
          onChange={setConfig}
          appId={appId}
        />
      );
      break;
    }
    case 'EventTriggerInspector': {
      body = <EventTriggerInspector />;
      break;
    }
    default: {
      body = (
        <DynamicConfigForm
          schema={desc.configSchema as unknown as JsonSchema}
          value={config}
          onChange={setConfig}
          hiddenFields={hiddenFields}
          appId={appId}
          connectionIdForVariables={
            typeof config.connection_id === 'string' ? config.connection_id : undefined
          }
          agentIdForVariables={
            typeof config.agent_id === 'string' && config.agent_id
              ? config.agent_id
              : undefined
          }
          templateNameForVariables={
            typeof config.template_name === 'string' ? config.template_name : undefined
          }
          payloadFieldOptions={fieldOptions}
        />
      );
    }
  }

  // Note on attempt policy: dispatch-node descriptors expose
  // ``attempt_policy`` as a config-schema field with
  // ``x-type: attempt_policy``, so DynamicConfigForm renders the
  // AttemptPolicyEditor inline through the FieldRenderer. We don't emit a
  // separate panel-level editor — that would render the same control twice
  // for any dispatch node whose preferredEditor falls through to the
  // default schema form.

  const emptyState = desc.editorHints?.emptyStateMessage as string | undefined;

  const preview = getPreviewForNode(node.type);

  // The standard inspector form keeps its fixed width. When a preview exists
  // it loses its own left border (the 2-pane wrapper owns that) so the seam
  // sits between the form and the preview, not before the form.
  const panel = (
    <div
      className={cn(
        'flex h-full w-[var(--inspector-width-node)] flex-col gap-3 overflow-y-auto p-4',
        !preview && 'border-l border-[var(--border-subtle)]',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-medium text-[var(--text-primary)]">
            {desc.displayLabel ?? desc.label}
          </div>
          <div className="truncate text-xs text-[var(--text-secondary)]">
            {desc.nodeType}
          </div>
        </div>
        {closeButton}
      </div>
      {readOnly ? (
        <div className="flex items-center justify-between gap-2 rounded-[var(--radius-default)] bg-[var(--bg-tertiary)] p-2 text-xs text-[var(--text-secondary)]">
          <span>Read-only — switch to Edit to change this node.</span>
          <button
            type="button"
            onClick={() => setViewMode('edit')}
            className="text-xs font-medium text-[var(--color-brand)] hover:underline"
          >
            Switch to Edit
          </button>
        </div>
      ) : null}
      {desc.authoringStatus === 'hidden' ? (
        <p className="rounded-[var(--radius-default)] bg-[var(--bg-warning-soft)] p-2 text-xs text-[var(--text-warning)]">
          This node is hidden from the palette. Existing definitions still
          execute, but new authoring is disabled.
        </p>
      ) : null}
      {emptyState ? (
        <p className="rounded-[var(--radius-default)] bg-[var(--bg-tertiary)] p-2 text-xs text-[var(--text-secondary)]">
          {emptyState}
        </p>
      ) : null}
      {/* Browser-native fieldset disable: every form input + button inside
       *  becomes non-interactive when `disabled` is set. Cheaper than
       *  threading a `readOnly` prop through every specialised editor. */}
      <fieldset disabled={readOnly} className="contents">
        <FieldSpotlightProvider fields={upstreamData?.fields ?? []}>
          {body}
        </FieldSpotlightProvider>
        {desc.requiredPayloadFields && desc.requiredPayloadFields.length > 0 ? (
          <FieldHint
            label="Requires payload fields"
            fields={desc.requiredPayloadFields}
          />
        ) : null}
        {desc.emittedPayloadFields && desc.emittedPayloadFields.length > 0 ? (
          <FieldHint
            label="Emits payload fields"
            fields={desc.emittedPayloadFields}
          />
        ) : null}
      </fieldset>
    </div>
  );

  if (!preview) return panel;

  // 2-pane shell: form (fixed width) + drag handle + preview (remaining
  // space). The outer row owns the total `inspectorWidth` and the left
  // border so the docked panel reads as one unit.
  return (
    <div
      className="flex h-full shrink-0 border-l border-[var(--border-subtle)]"
      style={{ width: resize.width }}
    >
      {panel}
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize inspector"
        onPointerDown={resize.onResizePointerDown}
        onPointerMove={resize.onResizePointerMove}
        onPointerUp={resize.onResizePointerUp}
        className="group relative w-1.5 shrink-0 cursor-col-resize border-l border-[var(--border-subtle)] bg-transparent"
      >
        <span className="absolute left-0 top-1/2 h-10 w-0.5 -translate-y-1/2 rounded bg-[var(--border-default)] group-hover:bg-[var(--color-brand)]" />
      </div>
      <div className="min-w-0 flex-1 bg-[var(--bg-primary)]">{preview(config)}</div>
    </div>
  );
}

function FieldHint({ label, fields }: { label: string; fields: string[] }) {
  return (
    <InspectorSection title={label}>
      <div className="flex flex-wrap gap-1">
        {fields.map((f) => (
          <code
            key={f}
            className="rounded-[var(--radius-default)] bg-[var(--bg-elevated)] px-1.5 py-0.5 text-[11px] text-[var(--text-primary)]"
          >
            {f}
          </code>
        ))}
      </div>
    </InspectorSection>
  );
}
