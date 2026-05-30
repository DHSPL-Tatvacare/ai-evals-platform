import { describe, expect, it } from 'vitest';

import { deriveContextUsage } from '@/features/sherlock/contextUsage';
import type {
  CompactionPart,
  SherlockPart,
  StepFinishPart,
} from '@/features/sherlock/generated/sherlockContract';

const BASE = { chat_session_id: 's', created_at: 0 } as const;

function stepFinish(seq: number, ctx: number | null, threshold: number | null): StepFinishPart {
  return {
    ...BASE,
    id: `sf-${seq}`,
    seq,
    type: 'step_finish',
    turn_id: 't',
    status: 'done',
    context_tokens: ctx ?? undefined,
    context_token_threshold: threshold ?? undefined,
  };
}
function compaction(seq: number, status: 'running' | 'done'): CompactionPart {
  return { ...BASE, id: `cp-${seq}`, seq, type: 'compaction', status, summary: '', tokens_before: 20000 };
}

describe('deriveContextUsage', () => {
  it('returns empty usage when there is no step_finish', () => {
    expect(deriveContextUsage([])).toEqual({ tokensUsed: null, threshold: null, compacting: false });
  });

  it('reads the latest step_finish context (by seq)', () => {
    const parts: SherlockPart[] = [stepFinish(1, 5000, 20000), stepFinish(3, 11000, 20000)];
    expect(deriveContextUsage(parts)).toEqual({ tokensUsed: 11000, threshold: 20000, compacting: false });
  });

  it('flags compacting while the latest compaction part is running', () => {
    const parts: SherlockPart[] = [stepFinish(1, 18000, 20000), compaction(2, 'running')];
    expect(deriveContextUsage(parts).compacting).toBe(true);
  });

  it('clears compacting once the compaction part is done', () => {
    const parts: SherlockPart[] = [stepFinish(1, 18000, 20000), compaction(2, 'done')];
    expect(deriveContextUsage(parts).compacting).toBe(false);
  });

  it('leaves threshold null when a step_finish omits it', () => {
    expect(deriveContextUsage([stepFinish(1, 5000, null)])).toEqual({
      tokensUsed: 5000,
      threshold: null,
      compacting: false,
    });
  });
});
