import { describe, expect, it } from 'vitest';

import { upstreamPayloadFields } from '@/features/orchestration/components/editors/upstreamPayloadFields';
import type {
  WorkflowDefinitionEdge,
  WorkflowDefinitionNode,
} from '@/features/orchestration/types';

function node(
  id: string,
  type: string,
  config: Record<string, unknown> = {},
): WorkflowDefinitionNode {
  return { id, type, position: { x: 0, y: 0 }, data: {}, config };
}

function edge(id: string, source: string, target: string): WorkflowDefinitionEdge {
  return { id, source, target, output_id: 'default' };
}

describe('upstreamPayloadFields', () => {
  it('collects payload_fields declared on an upstream source node', () => {
    const nodes = [
      node('src', 'source.dataset', { payload_fields: ['phone', 'tier', 'score'] }),
      node('cond', 'logic.conditional', {}),
    ];
    const edges = [edge('e1', 'src', 'cond')];
    expect(upstreamPayloadFields('cond', nodes, edges)).toEqual([
      'phone',
      'score',
      'tier',
    ]);
  });

  it('collects keys emitted by upstream messaging and voice dispatch nodes', () => {
    const nodes = [
      node('src', 'source.dataset', { payload_fields: ['phone'] }),
      node('wa', 'messaging.send_whatsapp_template', {}),
      node('call', 'voice.place_call', {}),
      node('cond', 'logic.conditional', {}),
    ];
    const edges = [
      edge('e1', 'src', 'wa'),
      edge('e2', 'wa', 'call'),
      edge('e3', 'call', 'cond'),
    ];
    const fields = upstreamPayloadFields('cond', nodes, edges);
    expect(fields).toContain('phone');
    expect(fields).toContain('steps.wa.wa_button_id');
    expect(fields).toContain('steps.wa.wa_reply_text');
    expect(fields).toContain('steps.call.voice_outcome');
  });

  it('walks transitively and ignores downstream nodes', () => {
    const nodes = [
      node('src', 'source.dataset', { payload_fields: ['phone'] }),
      node('wa', 'messaging.send_whatsapp_template', {}),
      node('cond', 'logic.conditional', {}),
      node('downstream', 'voice.place_call', {}),
    ];
    const edges = [
      edge('e1', 'src', 'wa'),
      edge('e2', 'wa', 'cond'),
      edge('e3', 'cond', 'downstream'),
    ];
    const fields = upstreamPayloadFields('cond', nodes, edges);
    expect(fields).toContain('steps.wa.wa_button_id');
    // downstream voice node is NOT upstream — its key must not appear.
    expect(fields).not.toContain('steps.downstream.voice_outcome');
  });

  it('returns an empty list when there is no upstream', () => {
    const nodes = [node('cond', 'logic.conditional', {})];
    expect(upstreamPayloadFields('cond', nodes, [])).toEqual([]);
  });
});
