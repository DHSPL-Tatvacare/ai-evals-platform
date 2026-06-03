/** Turn-grouped chat renderer: specialist blocks, charts, cost, copy.
 *  Pure render over the flat typed Part stream — streamStore stays the only state. */
import { AlertCircle, RotateCcw } from 'lucide-react';

import { Button } from '@/components/ui';
import { CostChip } from '@/features/cost/components/CostChip';
import { ThinkingIndicator } from '@/features/chat-widget/components/ThinkingIndicator';

import { CopyButton } from './components/CopyButton';
import { SpecialistGroup, type SpecialistPart } from './components/SpecialistGroup';
import {
  AssistantMarkdown,
  CanvasChangeCard,
  ChartCard,
  CompactionMarker,
  ReasoningBlock,
} from './components/parts';
import { phrasesForContext } from './contextualPhrases';
import { groupPartsIntoTurns, type Turn } from './grouping';
import type {
  AssistantTextPart,
  CompactionPart,
  ErrorPart,
  SherlockPart,
} from './generated/sherlockContract';

interface TurnListProps {
  parts: SherlockPart[];
  appId: string;
  sessionId: string | null;
  streaming: boolean;
  onRetry: () => void;
  /** Just-sent message, rendered as an optimistic bubble until the server echoes
   *  it. Client-only; never enters streamStore. */
  pendingUserText?: string | null;
  /** The client turn id of the in-flight send. The server echoes the user_message
   *  with id `user-${client_turn_id}` (see sherlock_v3/runtime.py), so the bubble
   *  yields by matching that exact id — the real contract, not a heuristic. */
  pendingTurnId?: string | null;
}

const FAILED_STATUSES = new Set(['error', 'degraded', 'interrupted', 'failed']);

function isSpecialistPart(part: SherlockPart): part is SpecialistPart {
  return part.type === 'subtask' || part.type === 'retry';
}

function AssistantAnswer({ part }: { part: AssistantTextPart }) {
  return <AssistantMarkdown part={part} />;
}

function renderAssistantBody(turn: Turn, appId: string, sessionId: string | null, settled: boolean) {
  // Specialists narrate live as ONE consultation block. The answer — prose, then
  // charts — is held until the turn settles and rendered once, after the
  // consultation. Charts never interleave mid-consultation or precede the answer.
  const blocks: React.ReactNode[] = [];
  const specialistParts = turn.parts.filter(isSpecialistPart);
  if (specialistParts.length > 0) {
    blocks.push(<SpecialistGroup key="sg" parts={specialistParts} settled={settled} />);
  }
  if (!settled) return blocks;

  for (const part of turn.parts) {
    if (part.type === 'reasoning') {
      blocks.push(<ReasoningBlock key={part.id} part={part} />);
    } else if (part.type === 'assistant_text') {
      blocks.push(<AssistantAnswer key={part.id} part={part} />);
    }
  }
  for (const part of turn.parts) {
    if (part.type === 'chart') {
      blocks.push(<ChartCard key={part.id} part={part} appId={appId} sessionId={sessionId} />);
    } else if (part.type === 'canvas_patch') {
      blocks.push(<CanvasChangeCard key={part.id} part={part} />);
    }
  }
  return blocks;
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end" data-testid="user-bubble">
      <div className="max-w-[85%] rounded-2xl rounded-br-md border border-[color-mix(in_srgb,var(--interactive-primary)_35%,transparent)] bg-[color-mix(in_srgb,var(--interactive-primary)_14%,var(--bg-primary))] px-3 py-1.5 text-[12px] leading-relaxed text-[var(--text-primary)] whitespace-pre-wrap break-words">
        {text}
      </div>
    </div>
  );
}

function UserTurn({ turn }: { turn: Turn }) {
  const text = turn.parts
    .map((p) => (p.type === 'user_message' ? p.text : ''))
    .join('');
  return <UserBubble text={text} />;
}

function AssistantTurn({
  turn,
  appId,
  sessionId,
  streaming,
  isLast,
  onRetry,
}: {
  turn: Turn;
  appId: string;
  sessionId: string | null;
  streaming: boolean;
  isLast: boolean;
  onRetry: () => void;
}) {
  const status = turn.stepFinish?.status;
  const failed = status ? FAILED_STATUSES.has(status) : false;
  const turnId = turn.stepFinish?.turn_id ?? null;
  // The live turn is the last one still streaming with no step_finish yet.
  // While live, specialist groups stay expanded (settled=false); they collapse
  // to a one-line summary only once the turn returns to the supervisor (done).
  const isLiveTurn = streaming && isLast && !turn.stepFinish;
  const settled = !isLiveTurn;
  // The shimmer narrates specialist work; once the final answer starts
  // streaming it owns the space, so the shimmer steps aside (no glass below
  // the growing answer). While a specialist group is present it is the live
  // narrator (one shimmering "consulting…" row), so the standalone glass yields
  // to it — exactly one shimmer line at a time.
  const answerStreaming = turn.parts.some((p) => p.type === 'assistant_text');
  const hasSpecialist = turn.parts.some(isSpecialistPart);
  // Glass before any specialist (initial thinking) AND while the held answer is
  // being composed (specialists done, not yet settled) — so it never looks frozen.
  const showThinking = isLiveTurn && ((!answerStreaming && !hasSpecialist) || answerStreaming);

  // Action bar below a finished message: copy + cost. Driven by the persisted
  // parts (answer text + step_finish.turn_id), so it's identical across live
  // stream / replay / hydration.
  const answerText = turn.parts
    .filter((p): p is AssistantTextPart => p.type === 'assistant_text')
    .map((p) => p.text ?? '')
    .join('');
  const showActions = settled && (answerText.trim() !== '' || !!turnId);

  // One error region: the real error message (from the error Part) plus a Retry
  // control when this is the last turn. Collapses the former banner + pill + card.
  const errorPart = turn.parts.find((p): p is ErrorPart => p.type === 'error');
  const errorMessage = errorPart?.message ?? (failed ? (status ?? 'error') : null);
  const showError = settled && errorMessage !== null;

  return (
    <div className="w-full">
      <div className="flex min-w-0 flex-col gap-2.5">
        {renderAssistantBody(turn, appId, sessionId, settled)}

        {showThinking ? <ThinkingIndicator phrases={phrasesForContext(turn.parts)} /> : null}

        {showActions ? (
          <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
            {answerText.trim() ? <CopyButton text={answerText} alwaysVisible /> : null}
            {turnId ? (
              <CostChip ownerType="sherlock_turn" ownerId={turnId} className="lowercase" />
            ) : null}
          </div>
        ) : null}

        {showError ? (
          <div
            className="flex items-start gap-3 rounded-2xl border border-[color-mix(in_srgb,var(--interactive-danger)_30%,transparent)] bg-[color-mix(in_srgb,var(--interactive-danger)_6%,var(--bg-primary))] px-4 py-3 text-[13px] text-[var(--text-primary)]"
            data-part-type="error"
            data-source={errorPart?.source}
            role="alert"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--interactive-danger)]" />
            <span className="min-w-0 flex-1 whitespace-pre-wrap break-words leading-relaxed">
              {errorMessage}
            </span>
            {isLast ? (
              <Button variant="ghost" size="sm" icon={RotateCcw} onClick={onRetry}>
                Retry
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function TurnList({ parts, appId, sessionId, streaming, onRetry, pendingUserText, pendingTurnId }: TurnListProps) {
  const turns = groupPartsIntoTurns(parts);
  const last = turns[turns.length - 1];
  // The optimistic bubble shows from send until the server's user_message echo —
  // whose id is `user-${client_turn_id}` (== pendingTurnId) — lands in `parts`.
  // Reconcile by that exact id (the real contract); the grouped UserTurn then owns
  // the bubble. No text/count heuristic, retry-safe, no duplicate.
  const echoId = pendingTurnId != null ? `user-${pendingTurnId}` : null;
  const echoArrived = echoId != null && parts.some((p) => p.id === echoId);
  const showPending = streaming && !!pendingUserText && pendingUserText.trim() !== '' && !echoArrived;
  const trailingThinking = streaming && !showPending && (!last || last.role === 'user');

  return (
    <div className="flex flex-col gap-5">
      {turns.map((turn, i) => {
        const isLast = i === turns.length - 1;
        if (turn.role === 'compaction') {
          const compaction = turn.parts.find(
            (p): p is CompactionPart => p.type === 'compaction',
          );
          return compaction ? (
            <CompactionMarker key={turn.id} part={compaction} />
          ) : null;
        }
        if (turn.role === 'user') {
          return <UserTurn key={turn.id} turn={turn} />;
        }
        return (
          <AssistantTurn
            key={turn.id}
            turn={turn}
            appId={appId}
            sessionId={sessionId}
            streaming={streaming}
            isLast={isLast}
            onRetry={onRetry}
          />
        );
      })}

      {showPending ? (
        <>
          <UserBubble text={pendingUserText as string} />
          <div className="w-full">
            <ThinkingIndicator />
          </div>
        </>
      ) : trailingThinking ? (
        <div className="w-full">
          <ThinkingIndicator />
        </div>
      ) : null}
    </div>
  );
}
