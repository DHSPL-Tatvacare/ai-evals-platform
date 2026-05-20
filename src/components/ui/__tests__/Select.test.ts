import { describe, expect, it } from 'vitest';
import { EMPTY_OPTION_VALUE, fromRadixValue, toRadixValue } from '../selectValue';

describe('Select empty-value contract', () => {
  it('never hands Radix an empty-string Item value', () => {
    expect(EMPTY_OPTION_VALUE).not.toBe('');
    expect(toRadixValue('')).toBe(EMPTY_OPTION_VALUE);
  });

  it('passes non-empty values through unchanged in both directions', () => {
    expect(toRadixValue('sent')).toBe('sent');
    expect(fromRadixValue('sent')).toBe('sent');
  });

  it('maps the sentinel back to the empty string callers expect', () => {
    expect(fromRadixValue(EMPTY_OPTION_VALUE)).toBe('');
  });
});
