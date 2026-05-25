import { describe, expect, it } from 'vitest';

import type {
  UpstreamField,
  UpstreamUnresolved,
} from '@/services/api/orchestration';
import type {
  WorkflowDefinitionEdge,
  WorkflowDefinitionNode,
} from '@/features/orchestration/types';

import {
  extractTemplateVariables,
  extractUpstreamSubgraph,
  lintUnknownVariables,
  parentLockStatus,
  saveAsCollides,
  sourceGroupLabel,
  suggestKnownVariable,
  toVariableInfo,
} from './upstreamVariables';

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

function field(path: string, extra: Partial<UpstreamField> = {}): UpstreamField {
  return { path, type: 'text', source: 'cohort', sourceNodeId: 'n', ...extra };
}

describe('extractUpstreamSubgraph', () => {
  it('collects ancestor nodes transitively and excludes downstream nodes', () => {
    const nodes = [
      node('src', 'source.cohort', { mode: 'saved' }),
      node('filter', 'logic.filter'),
      node('agent', 'llm.extract'),
      node('after', 'voice.place_call'),
    ];
    const edges = [
      edge('e1', 'src', 'filter'),
      edge('e2', 'filter', 'agent'),
      edge('e3', 'agent', 'after'),
    ];
    const sub = extractUpstreamSubgraph('agent', nodes, edges);
    expect(sub.nodes.map((n) => n.id).sort()).toEqual(['filter', 'src']);
    // The target node is excluded so editing its own config never refetches.
    expect(sub.nodes.map((n) => n.id)).not.toContain('agent');
    // Downstream node is excluded.
    expect(sub.nodes.map((n) => n.id)).not.toContain('after');
  });

  it('includes only the edges that wire the upstream chain into the target', () => {
    const nodes = [
      node('src', 'source.cohort'),
      node('filter', 'logic.filter'),
      node('agent', 'llm.extract'),
      node('after', 'voice.place_call'),
    ];
    const edges = [
      edge('e1', 'src', 'filter'),
      edge('e2', 'filter', 'agent'),
      edge('e3', 'agent', 'after'),
    ];
    const sub = extractUpstreamSubgraph('agent', nodes, edges);
    expect(sub.edges.map((e) => e.id).sort()).toEqual(['e1', 'e2']);
    expect(sub.edges.map((e) => e.id)).not.toContain('e3');
  });

  it('returns empty nodes and edges when the target has no upstream', () => {
    const nodes = [node('agent', 'llm.extract')];
    const sub = extractUpstreamSubgraph('agent', nodes, []);
    expect(sub.nodes).toEqual([]);
    expect(sub.edges).toEqual([]);
  });
});

describe('extractTemplateVariables', () => {
  it('extracts unique trimmed variable names, including dotted paths', () => {
    const vars = extractTemplateVariables(
      'Hi {{first_name}}, {{ intent.category }} and {{first_name}} again',
    );
    expect(vars).toEqual(['first_name', 'intent.category']);
  });

  it('returns an empty array when there are no placeholders', () => {
    expect(extractTemplateVariables('no variables here')).toEqual([]);
  });
});

describe('lintUnknownVariables', () => {
  it('flags an unknown variable when the resolver returned fields', () => {
    const fields = [field('last_message'), field('first_name')];
    const unknown = lintUnknownVariables(
      'Classify {{last_message}} from {{lastmessage}}',
      fields,
    );
    expect(unknown).toEqual(['lastmessage']);
  });

  it('returns no findings when every referenced variable is known', () => {
    const fields = [field('last_message')];
    expect(lintUnknownVariables('Use {{last_message}}', fields)).toEqual([]);
  });

  it('is OFF when fields are empty (event upstream / no upstream)', () => {
    // The resolver returned no fields — an event upstream contributes only
    // `unresolved`. Lint must NOT scream that every {{var}} is unknown.
    expect(lintUnknownVariables('Use {{anything}} and {{else}}', [])).toEqual([]);
  });
});

describe('suggestKnownVariable', () => {
  const fields = [field('last_message'), field('first_name')];

  it('suggests the known field that differs only by punctuation/case', () => {
    expect(suggestKnownVariable('lastmessage', fields)).toBe('last_message');
    expect(suggestKnownVariable('First_Name', fields)).toBe('first_name');
  });

  it('returns null when nothing is close', () => {
    expect(suggestKnownVariable('xyz', fields)).toBeNull();
  });
});

describe('parentLockStatus', () => {
  it('is "no-upstream" only when there are no fields and nothing unresolved', () => {
    expect(parentLockStatus([], [])).toBe('no-upstream');
  });

  it('is "unresolved-only" for an event upstream with no resolvable fields', () => {
    const unresolved: UpstreamUnresolved[] = [
      { nodeId: 'evt', label: 'Event trigger', reason: 'unknown until run' },
    ];
    // Valid-but-unresolved — never reported as "no fields".
    expect(parentLockStatus([], unresolved)).toBe('unresolved-only');
  });

  it('is "resolved" whenever any fields are present, even alongside unresolved', () => {
    const unresolved: UpstreamUnresolved[] = [
      { nodeId: 'evt', label: 'Event trigger', reason: 'unknown until run' },
    ];
    expect(parentLockStatus([field('a')], [])).toBe('resolved');
    expect(parentLockStatus([field('a')], unresolved)).toBe('resolved');
  });
});

describe('saveAsCollides', () => {
  const fields = [field('first_name'), field('intent.category')];

  it('does not collide when the namespace is empty', () => {
    expect(saveAsCollides(undefined, fields)).toBe(false);
    expect(saveAsCollides('', fields)).toBe(false);
  });

  it('collides when the namespace equals an upstream top-level key', () => {
    expect(saveAsCollides('first_name', fields)).toBe(true);
    // top-level segment of a dotted upstream path
    expect(saveAsCollides('intent', fields)).toBe(true);
  });

  it('does not collide with a fresh namespace', () => {
    expect(saveAsCollides('analysis', fields)).toBe(false);
  });
});

describe('toVariableInfo / sourceGroupLabel', () => {
  it('maps an upstream field to the VariablePickerPopover VariableInfo shape', () => {
    const info = toVariableInfo(
      field('intent.category', { type: 'enum', source: 'step', sampleValue: 'billing' }),
    );
    expect(info.key).toBe('intent.category');
    expect(info.valueType).toBe('enum');
    expect(info.category).toBe(sourceGroupLabel('step'));
    expect(info.example).toBe('billing');
  });

  it('labels each source group', () => {
    expect(sourceGroupLabel('cohort')).toBe('Cohort fields');
    expect(sourceGroupLabel('dataset')).toBe('Dataset columns');
    expect(sourceGroupLabel('static')).toBe('Record fields');
    expect(sourceGroupLabel('step')).toBe('Earlier steps');
  });
});
