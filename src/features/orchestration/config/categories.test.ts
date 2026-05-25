import { describe, expect, it } from 'vitest';

import { getCategoryDef } from './categories';

describe('getCategoryDef — AI category gradient identity', () => {
  it('exposes a vibrant gradient fill + soft gradient surface for ai', () => {
    const ai = getCategoryDef('ai');
    expect(ai.iconBgGradientVar).toBe('var(--gradient-node-ai)');
    expect(ai.surfaceGradientVar).toBe('var(--surface-node-ai)');
  });

  it('gives ai a distinct purple accent, not the shared indigo info token', () => {
    expect(getCategoryDef('ai').accentVar).toBe('var(--color-brand-primary)');
    expect(getCategoryDef('dispatch').accentVar).toBe('var(--color-info)');
  });

  it('exposes a gradient border for ai only', () => {
    expect(getCategoryDef('ai').borderGradientVar).toBe('var(--gradient-node-ai)');
    expect(getCategoryDef('dispatch').borderGradientVar).toBeUndefined();
  });

  it('leaves non-ai categories without gradient fields', () => {
    expect(getCategoryDef('dispatch').iconBgGradientVar).toBeUndefined();
    expect(getCategoryDef('mutation').surfaceGradientVar).toBeUndefined();
  });
});
