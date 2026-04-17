import { describe, expect, test } from 'vitest';

import {
  SHERLOCK_ERROR_PHRASES,
  SHERLOCK_THINKING_PHRASES,
  phrasesForContext,
} from './thinkingPhrases';
import type { MessagePart } from './types';

describe('phrasesForContext', () => {
  test('empty parts → generic pool', () => {
    expect(phrasesForContext([])).toBe(SHERLOCK_THINKING_PHRASES);
  });

  test('last part is text → generic pool', () => {
    const parts: MessagePart[] = [
      { type: 'text', content: 'hello' },
    ];
    expect(phrasesForContext(parts)).toBe(SHERLOCK_THINKING_PHRASES);
  });

  test('known tool (data_query) maps to analytics pool', () => {
    const parts: MessagePart[] = [
      { type: 'tool-call', toolCallId: 't1', toolName: 'data_query', state: 'completed' },
    ];
    const pool = phrasesForContext(parts);
    expect(pool).not.toBe(SHERLOCK_THINKING_PHRASES);
    expect(pool.some((p) => p.toLowerCase().includes('interrogating'))).toBe(true);
  });

  test('known tool (catalog_inspect) maps to catalog pool', () => {
    const parts: MessagePart[] = [
      { type: 'tool-call', toolCallId: 't1', toolName: 'catalog_inspect', state: 'completed' },
    ];
    const pool = phrasesForContext(parts);
    expect(pool.some((p) => p.toLowerCase().includes('records'))).toBe(true);
  });

  test('errored tool → error pool', () => {
    const parts: MessagePart[] = [
      { type: 'tool-call', toolCallId: 't1', toolName: 'data_query', state: 'error' },
    ];
    expect(phrasesForContext(parts)).toBe(SHERLOCK_ERROR_PHRASES);
  });

  test('unknown tool name → generic pool fallback', () => {
    const parts: MessagePart[] = [
      { type: 'tool-call', toolCallId: 't1', toolName: 'mystery_tool', state: 'completed' },
    ];
    expect(phrasesForContext(parts)).toBe(SHERLOCK_THINKING_PHRASES);
  });
});
