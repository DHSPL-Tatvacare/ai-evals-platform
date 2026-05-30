import { describe, expect, it } from 'vitest';

import { deriveSpotlightState } from './Canvas';

describe('deriveSpotlightState', () => {
  it('returns undefined when neither spotlight nor highlight is active', () => {
    expect(deriveSpotlightState('a', null, new Set())).toBeUndefined();
  });

  it('spotlight wins: focused node is on, others dim (highlight ignored)', () => {
    const highlighted = new Set(['a', 'b']);
    expect(deriveSpotlightState('a', 'b', highlighted)).toBe('dim');
    expect(deriveSpotlightState('b', 'b', highlighted)).toBe('on');
    expect(deriveSpotlightState('c', 'b', highlighted)).toBe('dim');
  });

  it('highlight rings changed nodes on without dimming the rest', () => {
    const highlighted = new Set(['a', 'b']);
    expect(deriveSpotlightState('a', null, highlighted)).toBe('on');
    expect(deriveSpotlightState('b', null, highlighted)).toBe('on');
    expect(deriveSpotlightState('c', null, highlighted)).toBeUndefined();
  });
});
