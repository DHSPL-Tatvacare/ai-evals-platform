import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import type { CanvasPatchOp } from '@/features/orchestration/copilot/canvasPatchSchema';
import type { NodeTypeDescriptor } from '@/features/orchestration/types';

import { chatWidgetCopy } from '../copy';
import {
  ChatCanvasChangeCard,
  buildCanvasChangeSummary,
} from './ChatCanvasChangeCard';

const descriptors = [
  { nodeType: 'messaging.send_whatsapp_template', displayLabel: 'Send WhatsApp template' },
  { nodeType: 'voice.place_call', displayLabel: 'Place call' },
] as unknown as NodeTypeDescriptor[];

const ops: CanvasPatchOp[] = [
  {
    op: 'add_node',
    node_id: 'n1',
    payload: { node_type: 'messaging.send_whatsapp_template', config: {} },
  },
  {
    op: 'add_node',
    node_id: 'n2',
    payload: { node_type: 'voice.place_call', config: {} },
  },
  {
    op: 'connect',
    node_id: 'n1',
    payload: {
      source_node_id: 'n1',
      output_id: 'default',
      target_node_id: 'n2',
      edge_id: 'e1',
    },
  },
  {
    op: 'remove_node',
    node_id: 'n3',
    payload: {},
  },
];

describe('buildCanvasChangeSummary', () => {
  it('renders summary text from descriptor labels, not raw type strings', () => {
    const { summary } = buildCanvasChangeSummary(ops, descriptors);
    expect(summary).toContain('Send WhatsApp template');
    expect(summary).not.toContain('messaging.send_whatsapp_template');
  });

  it('builds add / connect / remove chips with counts', () => {
    const { chips } = buildCanvasChangeSummary(ops, descriptors);
    const labels = chips.map((c) => c.label);
    expect(labels).toContain('+2 steps');
    expect(labels).toContain('↻1 connections');
    expect(labels).toContain('-1 steps');
  });

  it('falls back to node type when no descriptor is registered', () => {
    const { summary } = buildCanvasChangeSummary(
      [{ op: 'add_node', node_id: 'x', payload: { node_type: 'voice.place_call', config: {} } }],
      [],
    );
    expect(summary).toContain('voice.place_call');
  });
});

describe('ChatCanvasChangeCard', () => {
  const baseProps = {
    summary: 'Added Send WhatsApp template.',
    rationale: 'Because the operator asked to message contacts.',
    chips: [{ label: '+1 steps' }],
  };

  it('applied: title, chips, always-visible rationale, Undo + Show on canvas', () => {
    const onUndo = vi.fn();
    const onShowOnCanvas = vi.fn();
    render(
      <ChatCanvasChangeCard
        {...baseProps}
        variant="applied"
        onUndo={onUndo}
        onShowOnCanvas={onShowOnCanvas}
      />,
    );
    expect(screen.getByText(chatWidgetCopy.cardTitleApplied)).toBeInTheDocument();
    expect(screen.getByText('+1 steps')).toBeInTheDocument();
    expect(screen.getByText(chatWidgetCopy.rationaleLabel)).toBeInTheDocument();
    expect(screen.getByText(baseProps.rationale)).toBeInTheDocument();
    expect(screen.getByText(chatWidgetCopy.undo)).toBeInTheDocument();
    expect(screen.getByText(chatWidgetCopy.showOnCanvas)).toBeInTheDocument();
  });

  it('conflict: conflict copy with Redo on latest + Keep as is', () => {
    render(
      <ChatCanvasChangeCard
        {...baseProps}
        variant="conflict"
        onRedoOnLatest={vi.fn()}
        onKeepAsIs={vi.fn()}
      />,
    );
    expect(screen.getByText(chatWidgetCopy.conflict)).toBeInTheDocument();
    expect(screen.getByText(chatWidgetCopy.redoOnLatest)).toBeInTheDocument();
    expect(screen.getByText(chatWidgetCopy.keepAsIs)).toBeInTheDocument();
  });

  it('blocked: blocked copy with node name, no destructive actions', () => {
    render(
      <ChatCanvasChangeCard {...baseProps} variant="blocked" nodeName="Place call" />,
    );
    expect(screen.getByText(chatWidgetCopy.blocked, { exact: false })).toBeInTheDocument();
    expect(screen.getByText('Place call', { exact: false })).toBeInTheDocument();
    expect(screen.queryByText(chatWidgetCopy.undo)).not.toBeInTheDocument();
    expect(screen.queryByText(chatWidgetCopy.redoOnLatest)).not.toBeInTheDocument();
  });

  it('reverted: reverted copy with Redo on latest', () => {
    render(
      <ChatCanvasChangeCard
        {...baseProps}
        variant="reverted"
        onRedoOnLatest={vi.fn()}
      />,
    );
    expect(screen.getByText(chatWidgetCopy.reverted)).toBeInTheDocument();
    expect(screen.getByText(chatWidgetCopy.redoOnLatest)).toBeInTheDocument();
  });
});
