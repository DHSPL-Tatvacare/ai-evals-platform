import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { PageContext } from '@/features/orchestration/copilot/usePageContext';

import { BuilderContextChip } from './BuilderContextChip';

function fixture(viewMode: 'view' | 'edit'): Extract<PageContext, { kind: 'orchestration_builder' }> {
  return {
    kind: 'orchestration_builder',
    workflowId: 'wf_demo',
    versionId: 'v_1',
    workflowType: 'crm',
    appId: 'inside-sales',
    selectedNodeId: 'send_wati_1',
    workflowName: 'MQL Concierge',
    dataHash: 'h_abc',
    viewMode,
    definition: {
      nodes: [
        {
          id: 'send_wati_1',
          type: 'crm.send_wati',
          position: { x: 0, y: 0 },
          data: {},
          config: {},
        },
      ],
      edges: [],
    },
  };
}

describe('BuilderContextChip', () => {
  it('shows edit narration with the selected node and a dismiss button', () => {
    render(<BuilderContextChip pageContext={fixture('edit')} onDismiss={() => {}} />);
    expect(screen.getByText(/Editing: MQL Concierge/)).toBeInTheDocument();
    expect(screen.getByText(/selected:.*crm.send_wati/)).toBeInTheDocument();
    expect(screen.getByTestId('builder-context-chip-dismiss')).toBeInTheDocument();
  });

  it('shows view narration with no dismiss button', () => {
    const ctx = { ...fixture('view'), selectedNodeId: null };
    render(<BuilderContextChip pageContext={ctx} onDismiss={() => {}} />);
    expect(screen.getByText(/Viewing: MQL Concierge/)).toBeInTheDocument();
    expect(screen.getByText(/switch to Edit/i)).toBeInTheDocument();
    expect(screen.queryByTestId('builder-context-chip-dismiss')).toBeNull();
  });

  it('falls back to "no selection" when nothing is selected in edit mode', () => {
    const ctx = { ...fixture('edit'), selectedNodeId: null };
    render(<BuilderContextChip pageContext={ctx} onDismiss={() => {}} />);
    expect(screen.getByText(/no selection/)).toBeInTheDocument();
  });

  it('fires onDismiss exactly once when [×] is clicked', async () => {
    const onDismiss = vi.fn();
    render(<BuilderContextChip pageContext={fixture('edit')} onDismiss={onDismiss} />);
    await userEvent.click(screen.getByTestId('builder-context-chip-dismiss'));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
