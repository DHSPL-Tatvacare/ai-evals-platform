/**
 * Phase 3 — custom edge delete affordance.
 *
 * Each edge carries a hover "×" that removes it from the store. Gated on
 * edit mode so a published / view-mode canvas never exposes a destructive
 * one-click. Removal flows through `removeEdge`, leaving no orphan edge
 * behind (the Phase-5 lineage prerequisite).
 *
 * We render `CustomEdgeLabel` directly: the full `CustomEdge` wraps it in
 * `EdgeLabelRenderer`, a portal that only exists inside a fully-measured
 * `<ReactFlow>` — which jsdom never measures. The label component carries
 * the entire affordance, so testing it directly exercises the real code.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { CustomEdgeLabel } from '@/features/orchestration/components/CustomEdge';
import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';

describe('CustomEdge delete affordance', () => {
  beforeEach(() => {
    useWorkflowBuilderStore.getState().reset();
    useWorkflowBuilderStore.getState().setViewMode('edit');
    useWorkflowBuilderStore.getState().addEdge({
      id: 'e1',
      source: 'a',
      target: 'b',
      output_id: 'success',
    });
  });

  it('renders a delete button in edit mode and removes the edge on click', () => {
    render(
      <CustomEdgeLabel edgeId="e1" label="Success" editable labelX={0} labelY={0} />,
    );
    const btn = screen.getByRole('button', { name: /delete edge/i });
    expect(btn).toBeTruthy();
    fireEvent.click(btn);
    expect(useWorkflowBuilderStore.getState().edges).toHaveLength(0);
  });

  it('does not render the delete button in view mode', () => {
    render(
      <CustomEdgeLabel
        edgeId="e1"
        label="Success"
        editable={false}
        labelX={0}
        labelY={0}
      />,
    );
    expect(screen.queryByRole('button', { name: /delete edge/i })).toBeNull();
    // The output label still renders so a view-mode canvas reads its routing.
    expect(screen.getByText('Success')).toBeTruthy();
  });
});
