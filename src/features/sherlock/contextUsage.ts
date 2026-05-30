/** Derive the composer context-ring state from the part stream — pure, replay-safe.
 *  Fill rides on the latest step_finish (in lockstep with the compaction trigger);
 *  the compacting flag is the latest compaction part's running state. */
import type { SherlockPart } from './generated/sherlockContract';

export interface ContextUsage {
  tokensUsed: number | null;
  threshold: number | null;
  compacting: boolean;
}

export function deriveContextUsage(parts: readonly SherlockPart[]): ContextUsage {
  let tokensUsed: number | null = null;
  let threshold: number | null = null;
  let stepSeq = -1;
  let compactionSeq = -1;
  let compacting = false;

  for (const p of parts) {
    if (p.type === 'step_finish' && typeof p.context_tokens === 'number' && p.seq > stepSeq) {
      stepSeq = p.seq;
      tokensUsed = p.context_tokens;
      threshold = typeof p.context_token_threshold === 'number' ? p.context_token_threshold : null;
    } else if (p.type === 'compaction' && p.seq > compactionSeq) {
      compactionSeq = p.seq;
      compacting = (p.status ?? 'done') === 'running';
    }
  }

  return { tokensUsed, threshold, compacting };
}
