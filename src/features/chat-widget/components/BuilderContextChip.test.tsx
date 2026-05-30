import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import type { NodeTypeDescriptor } from '@/features/orchestration/types';
import type { PageContext } from '@/features/orchestration/copilot/usePageContext';

import { chatWidgetCopy } from '../copy';
import { BuilderContextChip } from './BuilderContextChip';

function descriptor(
  nodeType: string,
  displayLabel: string,
  displayCategory: NodeTypeDescriptor['displayCategory'],
): NodeTypeDescriptor {
  return {
    nodeType,
    workflowType: 'crm',
    displayLabel,
    displayCategory,
    description: '',
    authoringStatus: 'active',
    configSchema: {},
    editorHints: {},
    requiredPayloadFields: [],
    emittedPayloadFields: [],
    outputEdges: [],
    graphRules: {},
    runtimeContract: { executionKind: 'dispatch' },
    category: 'action',
    label: displayLabel,
  };
}

function fixture(
  viewMode: 'view' | 'edit',
): Extract<PageContext, { kind: 'orchestration_builder' }> {
  return {
    kind: 'orchestration_builder',
    workflowId: 'wf_demo',
    versionId: 'v_1',
    workflowType: 'crm',
    appId: 'inside-sales',
    selectedNodeId: null,
    workflowName: 'MQL Concierge',
    dataHash: 'abc1234567890def',
    viewMode,
    definition: {
      nodes: [
        { id: 'send_1', type: 'messaging.send_whatsapp_template', position: { x: 0, y: 0 }, data: {}, config: {} },
        { id: 'send_2', type: 'messaging.send_whatsapp_template', position: { x: 80, y: 0 }, data: {}, config: {} },
        { id: 'sink_1', type: 'sink.complete', position: { x: 160, y: 0 }, data: {}, config: {} },
      ],
      edges: [
        { id: 'e1', source: 'send_1', target: 'send_2', output_id: 'success' },
        { id: 'e2', source: 'send_2', target: 'sink_1', output_id: 'success' },
      ],
    },
  };
}

function seedPalette() {
  useWorkflowBuilderStore.getState().setPaletteCatalog([
    descriptor('messaging.send_whatsapp_template', 'Send WhatsApp', 'dispatch'),
    descriptor('sink.complete', 'Complete', 'termination'),
  ]);
}

describe('BuilderContextChip — on state', () => {
  beforeEach(() => {
    useWorkflowBuilderStore.getState().reset();
    seedPalette();
  });

  it('renders the verb + workflow name + workflow-type badge in edit mode', () => {
    render(<BuilderContextChip pageContext={fixture('edit')} working={false} />);
    expect(screen.getByText(/Editing · MQL Concierge/)).toBeInTheDocument();
    expect(screen.getByText('CRM')).toBeInTheDocument();
  });

  it('shows the viewing verb in view mode', () => {
    render(<BuilderContextChip pageContext={fixture('view')} working={false} />);
    expect(screen.getByText(/Viewing · MQL Concierge/)).toBeInTheDocument();
  });

  it('renders the type badge from the workflowType (clinical)', () => {
    const ctx = { ...fixture('edit'), workflowType: 'clinical' as const };
    render(<BuilderContextChip pageContext={ctx} working={false} />);
    expect(screen.getByText('Clinical')).toBeInTheDocument();
  });

  it('falls back to "Untitled workflow" when the name is blank', () => {
    const ctx = { ...fixture('edit'), workflowName: '   ' };
    render(<BuilderContextChip pageContext={ctx} working={false} />);
    expect(screen.getByText(/Editing · Untitled workflow/)).toBeInTheDocument();
  });

  it('derives the info line counts from the definition + dominant category', () => {
    render(<BuilderContextChip pageContext={fixture('edit')} working={false} />);
    expect(
      screen.getByText(
        chatWidgetCopy.infoLineTemplate({ steps: 3, count: 2, category: 'dispatch' }),
      ),
    ).toBeInTheDocument();
  });

  it('reads the working label while active', () => {
    render(<BuilderContextChip pageContext={fixture('edit')} working />);
    expect(screen.getByText(chatWidgetCopy.workingLabel)).toBeInTheDocument();
  });
});

describe('BuilderContextChip — canvas toggle', () => {
  beforeEach(() => {
    useWorkflowBuilderStore.getState().reset();
    seedPalette();
  });

  it('flips canvasContextEnabled off when the switch is toggled', async () => {
    expect(useWorkflowBuilderStore.getState().canvasContextEnabled).toBe(true);
    render(<BuilderContextChip pageContext={fixture('edit')} working={false} />);
    await userEvent.click(screen.getByTestId('builder-context-chip-switch'));
    expect(useWorkflowBuilderStore.getState().canvasContextEnabled).toBe(false);
  });

  it('renders the off line when canvas context is disabled', () => {
    useWorkflowBuilderStore.getState().setCanvasContextEnabled(false);
    render(<BuilderContextChip pageContext={fixture('edit')} working={false} />);
    expect(screen.getByText(chatWidgetCopy.canvasOffLine)).toBeInTheDocument();
  });

  it('flips canvasContextEnabled back on from the off state', async () => {
    useWorkflowBuilderStore.getState().setCanvasContextEnabled(false);
    render(<BuilderContextChip pageContext={fixture('edit')} working={false} />);
    await userEvent.click(screen.getByTestId('builder-context-chip-switch'));
    expect(useWorkflowBuilderStore.getState().canvasContextEnabled).toBe(true);
  });
});

describe('BuilderContextChip — selection scope', () => {
  beforeEach(() => {
    useWorkflowBuilderStore.getState().reset();
    seedPalette();
  });

  it('shows a scope chip with the descriptor label when a node is selected', () => {
    const ctx = { ...fixture('edit'), selectedNodeId: 'send_1' };
    render(<BuilderContextChip pageContext={ctx} working={false} />);
    expect(screen.getByText(/Focused on:/)).toBeInTheDocument();
    expect(screen.getByText('Send WhatsApp')).toBeInTheDocument();
  });

  it('clears the selection via the scope chip clear button', async () => {
    useWorkflowBuilderStore.getState().setSelectedNode('send_1');
    const ctx = { ...fixture('edit'), selectedNodeId: 'send_1' };
    render(<BuilderContextChip pageContext={ctx} working={false} />);
    await userEvent.click(screen.getByTestId('builder-context-chip-clear-scope'));
    expect(useWorkflowBuilderStore.getState().selectedNodeId).toBeNull();
  });

  it('hides the scope chip in the off state', () => {
    useWorkflowBuilderStore.getState().setCanvasContextEnabled(false);
    const ctx = { ...fixture('edit'), selectedNodeId: 'send_1' };
    render(<BuilderContextChip pageContext={ctx} working={false} />);
    expect(screen.queryByText(/Focused on:/)).toBeNull();
  });
});
