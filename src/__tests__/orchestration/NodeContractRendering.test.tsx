import { describe, expect, it, beforeEach, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { NodeConfigPanel } from '@/features/orchestration/components/NodeConfigPanel';
import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import type { CohortSource, NodeTypeDescriptor } from '@/features/orchestration/types';

vi.mock('@/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/hooks')>();
  return { ...actual, useCurrentAppId: () => 'inside-sales' };
});

const cohortSource: CohortSource = {
  sourceRef: 'crm.leads',
  displayLabel: 'CRM Leads',
  description: 'Live CRM lead table',
  kind: 'static',
  workflowTypes: ['crm'],
  appIds: ['inside-sales'],
  idColumn: 'lead_id',
  allowedPayloadColumns: ['name', 'phone'],
  allowedFilterColumns: ['stage'],
  allowedLookbackColumns: ['updated_at'],
  schemaDescriptor: null,
};

const cohortSourceTyped: CohortSource = {
  sourceRef: 'crm.leads_typed',
  displayLabel: 'CRM Leads (typed)',
  description: 'Source with schema descriptor',
  kind: 'static',
  workflowTypes: ['crm'],
  appIds: ['inside-sales'],
  idColumn: 'lead_id',
  allowedPayloadColumns: ['name', 'score'],
  allowedFilterColumns: ['name', 'score'],
  allowedLookbackColumns: [],
  schemaDescriptor: {
    columns: [
      { name: 'name', type: 'string' },
      { name: 'score', type: 'number' },
    ],
  },
};

vi.mock('@/features/orchestration/queries/cohorts', () => ({
  useCohortSources: () => ({ data: [cohortSource, cohortSourceTyped] }),
  useCohorts: () => ({ data: [] }),
  useCohort: () => ({ data: undefined }),
  useCohortColumnValues: () => ({
    options: [{ value: 'Alice', label: 'Alice' }, { value: 'Bob', label: 'Bob' }],
    loading: false,
    onSearchChange: () => undefined,
  }),
}));

function descriptor(
  override: Partial<NodeTypeDescriptor>,
): NodeTypeDescriptor {
  return {
    nodeType: override.nodeType ?? 'filter.eligibility',
    workflowType: '*',
    displayLabel: override.displayLabel ?? 'Eligibility Filter',
    displayCategory: override.displayCategory ?? 'qualification',
    description: override.description ?? '',
    authoringStatus: override.authoringStatus ?? 'active',
    configSchema: override.configSchema ?? {
      type: 'object',
      properties: { predicate: { type: 'object' } },
    },
    editorHints: override.editorHints ?? {},
    requiredPayloadFields: override.requiredPayloadFields ?? [],
    emittedPayloadFields: override.emittedPayloadFields ?? [],
    outputEdges: override.outputEdges ?? [],
    graphRules: override.graphRules ?? {},
    runtimeContract: override.runtimeContract ?? {
      executionKind: 'qualification',
    },
    category: override.category ?? 'filter',
    label: override.label ?? override.displayLabel ?? 'Eligibility Filter',
  };
}

describe('NodeConfigPanel — descriptor-driven rendering', () => {
  beforeEach(() => {
    useWorkflowBuilderStore.getState().reset();
  });

  it('renders the empty-state when no node is selected', () => {
    render(<NodeConfigPanel />);
    expect(
      screen.getByText('Select a node to edit its config.'),
    ).toBeInTheDocument();
  });

  it('uses the shared RuleSetBuilder for filter.eligibility', () => {
    const desc = descriptor({
      nodeType: 'filter.eligibility',
      editorHints: { preferredEditor: 'PredicateBuilder' },
    });
    const store = useWorkflowBuilderStore.getState();
    store.setPaletteCatalog([desc]);
    store.addNode({
      id: 'n1',
      type: 'filter.eligibility',
      position: { x: 0, y: 0 },
      data: { label: 'eligibility' },
      config: {},
    });
    store.setSelectedNode('n1');
    render(<NodeConfigPanel />);
    // RuleSetBuilder shows the Match ALL/ANY rule-set header and a stacked rule.
    expect(screen.getByText('of these rules')).toBeInTheDocument();
    expect(screen.getByText('Operator')).toBeInTheDocument();
  });

  it('uses ConditionalBranchesEditor for logic.conditional', () => {
    const desc = descriptor({
      nodeType: 'logic.conditional',
      displayLabel: 'Conditional Branch',
      displayCategory: 'routing',
      editorHints: { preferredEditor: 'ConditionalBranchesEditor' },
      runtimeContract: { executionKind: 'routing' },
      category: 'logic',
    });
    const store = useWorkflowBuilderStore.getState();
    store.setPaletteCatalog([desc]);
    store.addNode({
      id: 'n1',
      type: 'logic.conditional',
      position: { x: 0, y: 0 },
      data: { label: 'conditional' },
      config: { branches: [] },
    });
    store.setSelectedNode('n1');
    render(<NodeConfigPanel />);
    expect(screen.getByText('Add branch')).toBeInTheDocument();
    // The implicit default output is always shown.
    expect(screen.getByText('default')).toBeInTheDocument();
  });

  it('uses WaitConditionEditor for logic.wait', () => {
    const desc = descriptor({
      nodeType: 'logic.wait',
      displayLabel: 'Wait Condition',
      editorHints: { preferredEditor: 'WaitConditionEditor' },
      runtimeContract: {
        executionKind: 'suspension',
        supportsSuspendResume: true,
      },
    });
    const store = useWorkflowBuilderStore.getState();
    store.setPaletteCatalog([desc]);
    store.addNode({
      id: 'n1',
      type: 'logic.wait',
      position: { x: 0, y: 0 },
      data: { label: 'wait' },
      config: { mode: 'duration', duration_hours: 4 },
    });
    store.setSelectedNode('n1');
    render(<NodeConfigPanel />);
    expect(screen.getByPlaceholderText('hours to wait')).toBeInTheDocument();
  });

  it('shows the hidden-node warning when authoringStatus=hidden', () => {
    const desc = descriptor({
      nodeType: 'filter.consent_gate',
      displayLabel: 'Consent Gate',
      authoringStatus: 'hidden',
      editorHints: {
        emptyStateMessage:
          'Author-only gate — surfaces context for existing definitions.',
      },
    });
    const store = useWorkflowBuilderStore.getState();
    store.setPaletteCatalog([desc]);
    store.addNode({
      id: 'n1',
      type: 'filter.consent_gate',
      position: { x: 0, y: 0 },
      data: { label: 'consent' },
      config: {},
    });
    store.setSelectedNode('n1');
    render(<NodeConfigPanel />);
    // Hidden warning banner.
    expect(
      screen.getByText(/This node is hidden from the palette/i),
    ).toBeInTheDocument();
    // Editor-hints empty-state message — distinct from the warning.
    expect(
      screen.getByText(/Author-only gate/i),
    ).toBeInTheDocument();
  });

  it('surfaces requiredPayloadFields and emittedPayloadFields from the descriptor', () => {
    const desc = descriptor({
      nodeType: 'core.webhook_out',
      displayLabel: 'Webhook Dispatch',
      displayCategory: 'dispatch',
      configSchema: { type: 'object', properties: {} },
      requiredPayloadFields: ['recipient_id'],
      emittedPayloadFields: ['response_id'],
      runtimeContract: {
        executionKind: 'dispatch',
        supportsAttemptPolicy: true,
      },
      category: 'action',
    });
    const store = useWorkflowBuilderStore.getState();
    store.setPaletteCatalog([desc]);
    store.addNode({
      id: 'n1',
      type: 'core.webhook_out',
      position: { x: 0, y: 0 },
      data: { label: 'webhook' },
      config: {},
    });
    store.setSelectedNode('n1');
    render(<NodeConfigPanel />);
    expect(screen.getByText('Requires payload fields')).toBeInTheDocument();
    expect(screen.getByText('recipient_id')).toBeInTheDocument();
    expect(screen.getByText('Emits payload fields')).toBeInTheDocument();
    expect(screen.getByText('response_id')).toBeInTheDocument();
  });

  function mountSourceCohort(config: Record<string, unknown>) {
    const desc = descriptor({
      nodeType: 'source.cohort',
      displayLabel: 'Cohort Source',
      displayCategory: 'ingress',
      configSchema: { type: 'object', properties: {} },
      editorHints: { preferredEditor: 'SourceCohortPicker' },
      runtimeContract: { executionKind: 'entry_sql' },
      category: 'source',
    });
    const store = useWorkflowBuilderStore.getState();
    store.setPaletteCatalog([desc]);
    useWorkflowBuilderStore.setState({ workflowType: 'crm' });
    store.addNode({
      id: 'n1',
      type: 'source.cohort',
      position: { x: 0, y: 0 },
      data: { label: 'cohort' },
      config,
    });
    store.setSelectedNode('n1');
  }

  it('dispatches source.cohort to SourceCohortPicker with a mode toggle', () => {
    mountSourceCohort({ mode: 'inline', source_ref: '', payload_fields: [] });
    render(<NodeConfigPanel />);
    expect(screen.getByText('Audience')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Inline' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Saved' })).toBeInTheDocument();
  });

  it('shows the inline source picker by default and switches to the saved branch', () => {
    mountSourceCohort({ mode: 'inline', source_ref: '', payload_fields: [] });
    render(<NodeConfigPanel />);
    // Inline branch renders the source/filters sub-form.
    expect(screen.getByText('Source')).toBeInTheDocument();
    expect(screen.getByText('Filters')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Saved' }));

    // Store now carries mode='saved'.
    const updated = useWorkflowBuilderStore
      .getState()
      .nodes.find((n) => n.id === 'n1');
    expect((updated?.config as { mode?: string }).mode).toBe('saved');
    // Saved branch renders the saved-cohort empty state (no cohorts mocked).
    expect(screen.getByText(/No saved cohorts yet/i)).toBeInTheDocument();
    expect(screen.queryByText('Filters')).not.toBeInTheDocument();
  });

  it('shows async value combobox for a string column filter', () => {
    // Mount with a typed source that has a string column and an existing filter.
    const store = useWorkflowBuilderStore.getState();
    const desc = descriptor({
      nodeType: 'source.cohort',
      displayLabel: 'Cohort Source',
      displayCategory: 'ingress',
      configSchema: { type: 'object', properties: {} },
      editorHints: { preferredEditor: 'SourceCohortPicker' },
      runtimeContract: { executionKind: 'entry_sql' },
      category: 'source',
    });
    store.setPaletteCatalog([desc]);
    useWorkflowBuilderStore.setState({ workflowType: 'crm' });
    store.addNode({
      id: 'n2',
      type: 'source.cohort',
      position: { x: 0, y: 0 },
      data: { label: 'cohort' },
      config: {
        mode: 'inline',
        source_ref: 'crm.leads_typed',
        payload_fields: ['name', 'score'],
        filters: [{ column: 'name', op: 'eq', value: '' }],
      },
    });
    store.setSelectedNode('n2');
    render(<NodeConfigPanel />);
    // With a string column + eq op the Combobox renders a "select a value…" placeholder.
    expect(screen.getByText('select a value…')).toBeInTheDocument();
  });

  it('shows a numeric input for a number column filter', () => {
    const store = useWorkflowBuilderStore.getState();
    const desc = descriptor({
      nodeType: 'source.cohort',
      displayLabel: 'Cohort Source',
      displayCategory: 'ingress',
      configSchema: { type: 'object', properties: {} },
      editorHints: { preferredEditor: 'SourceCohortPicker' },
      runtimeContract: { executionKind: 'entry_sql' },
      category: 'source',
    });
    store.setPaletteCatalog([desc]);
    useWorkflowBuilderStore.setState({ workflowType: 'crm' });
    store.addNode({
      id: 'n3',
      type: 'source.cohort',
      position: { x: 0, y: 0 },
      data: { label: 'cohort' },
      config: {
        mode: 'inline',
        source_ref: 'crm.leads_typed',
        payload_fields: ['name', 'score'],
        filters: [{ column: 'score', op: 'gt', value: '' }],
      },
    });
    store.setSelectedNode('n3');
    render(<NodeConfigPanel />);
    // Number column renders a numeric input with placeholder "value".
    const inputs = screen.getAllByPlaceholderText('value');
    const numInput = inputs.find(
      (el) => el instanceof HTMLInputElement && el.type === 'number',
    );
    expect(numInput).toBeDefined();
  });

  it('narrows operator list by column type', () => {
    const store = useWorkflowBuilderStore.getState();
    const desc = descriptor({
      nodeType: 'source.cohort',
      displayLabel: 'Cohort Source',
      displayCategory: 'ingress',
      configSchema: { type: 'object', properties: {} },
      editorHints: { preferredEditor: 'SourceCohortPicker' },
      runtimeContract: { executionKind: 'entry_sql' },
      category: 'source',
    });
    store.setPaletteCatalog([desc]);
    useWorkflowBuilderStore.setState({ workflowType: 'crm' });
    store.addNode({
      id: 'n4',
      type: 'source.cohort',
      position: { x: 0, y: 0 },
      data: { label: 'cohort' },
      config: {
        mode: 'inline',
        source_ref: 'crm.leads_typed',
        payload_fields: ['name', 'score'],
        filters: [{ column: 'score', op: 'gt', value: 10 }],
      },
    });
    store.setSelectedNode('n4');
    render(<NodeConfigPanel />);
    // For a number column the operator select should NOT offer "contains" (string-only).
    expect(screen.queryByText('contains')).not.toBeInTheDocument();
    // But it should offer numeric comparators.
    expect(screen.getByText('gt')).toBeInTheDocument();
  });
});
