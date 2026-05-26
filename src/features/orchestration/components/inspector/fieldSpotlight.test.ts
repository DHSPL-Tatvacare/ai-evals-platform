import { describe, expect, it } from 'vitest';

import { indexFieldNodeIds } from './fieldSpotlight';

describe('indexFieldNodeIds', () => {
  it('maps each field path to its source node id', () => {
    const index = indexFieldNodeIds([
      { path: 'steps.voice.place_call-1.outcome', sourceNodeId: 'voice.place_call-1' },
      { path: 'lead_id', sourceNodeId: 'source.cohort-9' },
    ]);

    expect(index.get('steps.voice.place_call-1.outcome')).toBe('voice.place_call-1');
    expect(index.get('lead_id')).toBe('source.cohort-9');
  });

  it('returns undefined for an unknown path', () => {
    const index = indexFieldNodeIds([
      { path: 'first_name', sourceNodeId: 'source.cohort-9' },
    ]);
    expect(index.get('not_a_field')).toBeUndefined();
  });

  it('skips entries missing a path or source node id', () => {
    const index = indexFieldNodeIds([
      { path: '', sourceNodeId: 'n1' },
      { path: 'phone', sourceNodeId: '' },
      { path: 'email', sourceNodeId: 'n2' },
    ]);
    expect(index.size).toBe(1);
    expect(index.get('email')).toBe('n2');
  });
});
