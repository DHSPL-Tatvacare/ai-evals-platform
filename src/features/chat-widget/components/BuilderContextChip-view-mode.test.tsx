import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import type { NodeTypeDescriptor } from '@/features/orchestration/types';
import type { PageContext } from '@/features/orchestration/copilot/usePageContext';

import { BuilderContextChip } from './BuilderContextChip';

function descriptor(nodeType: string, displayLabel: string): NodeTypeDescriptor {
  return {
    nodeType,
    workflowType: 'crm',
    displayLabel,
    displayCategory: 'dispatch',
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
    dataHash: 'abc1234',
    viewMode,
    definition: {
      nodes: [
        { id: 'send_1', type: 'messaging.send_whatsapp_template', position: { x: 0, y: 0 }, data: {}, config: {} },
      ],
      edges: [],
    },
  };
}

describe('BuilderContextChip — view-mode verb', () => {
  beforeEach(() => {
    useWorkflowBuilderStore.getState().reset();
    useWorkflowBuilderStore
      .getState()
      .setPaletteCatalog([descriptor('messaging.send_whatsapp_template', 'Send WhatsApp')]);
  });

  it('says "Editing" when the view mode is edit', () => {
    render(<BuilderContextChip pageContext={fixture('edit')} working={false} />);
    expect(screen.getByText(/Editing · MQL Concierge/)).toBeInTheDocument();
  });

  it('says "Viewing" when the view mode is view', () => {
    render(<BuilderContextChip pageContext={fixture('view')} working={false} />);
    expect(screen.getByText(/Viewing · MQL Concierge/)).toBeInTheDocument();
  });

  it('keeps the verb visible regardless of view mode while the canvas toggle is on', () => {
    render(<BuilderContextChip pageContext={fixture('view')} working={false} />);
    expect(screen.getByTestId('builder-context-chip-switch')).toBeInTheDocument();
  });
});
