/**
 * Sherlock Part stream client — one POST per turn.
 *
 * Wire (per Phase 1B): backend yields SSE frames as
 *   event: <name>
 *   data:  <json>
 *
 * Event names we care about:
 *   - `session`        — session metadata, emitted once at stream start.
 *   - `part_added`     — new Part; data is {seq, part}.
 *   - `part_updated`   — existing Part replaced by id; data is {seq, part}.
 *   - `turn_terminal`  — final marker; data carries {status, last_error}.
 *
 * Anything else is logged + ignored. Malformed payloads or seq gaps
 * ask TanStack Query to invalidate the snapshot so the store re-seeds.
 *
 * Why fetch + ReadableStream rather than EventSource: EventSource cannot
 * carry a Bearer header, our auth model is Authorization-only. Same
 * constraint useRunStream solves the same way.
 */
import type { QueryClient } from '@tanstack/react-query';

import { logger } from '@/services/logger';
import { useAuthStore } from '@/stores/authStore';

import { validateSherlockPart } from './generated/sherlockContract.validator';
import { sherlockPartsQueryKeys } from './queries/parts';
import {
  useStreamStore,
  type StreamEvent,
} from './streamStore';

export type TerminalStatus = 'done' | 'error' | 'interrupted';

export interface TurnTerminal {
  status: TerminalStatus;
  lastError: string | null;
}

export interface StreamTurnOptions {
  appId: string;
  sessionId: string;
  turnId: string;
  /** Required for `operation: 'send'`; must be absent for `operation: 'resume'`. */
  message?: string;
  model: string;
  provider?: string;
  operation?: 'send' | 'resume';
  resumeFromSeq?: number;
  queryClient: QueryClient;
  /** Optional terminal callback for the host (status pill, error toast, etc.). */
  onTerminal?(payload: TurnTerminal): void;
}

export interface TurnStreamControls {
  abort(): void;
  done: Promise<TurnTerminal>;
}

/**
 * POST one turn to the chat/stream SSE endpoint and pipe every accepted
 * Part into the streamStore. Resolves once the stream emits its
 * `turn_terminal` frame or aborts.
 */
export function streamTurn(options: StreamTurnOptions): TurnStreamControls {
  const controller = new AbortController();
  let resolved = false;
  let terminal: TurnTerminal | null = null;
  let resolveDone: (t: TurnTerminal) => void = () => {};
  let rejectDone: (err: unknown) => void = () => {};
  const done = new Promise<TurnTerminal>((resolve, reject) => {
    resolveDone = resolve;
    rejectDone = reject;
  });

  const invalidateSnapshot = () => {
    void options.queryClient.invalidateQueries({
      queryKey: sherlockPartsQueryKeys.sessionParts(options.sessionId),
    });
  };

  const setStatus = useStreamStore.getState().setStatus;
  setStatus('streaming');

  const finalize = (payload: TurnTerminal) => {
    if (resolved) return;
    resolved = true;
    terminal = payload;
    setStatus(payload.status === 'error' ? 'error' : 'idle');
    options.onTerminal?.(payload);
    resolveDone(payload);
  };

  void (async () => {
    const token = useAuthStore.getState().accessToken;
    if (!token) {
      finalize({ status: 'error', lastError: 'No active session' });
      return;
    }
    const body = {
      appId: options.appId,
      sessionId: options.sessionId,
      turnId: options.turnId,
      operation: options.operation ?? 'send',
      message: options.message ?? null,
      model: options.model,
      provider: options.provider ?? null,
      resumeFromSeq: options.resumeFromSeq ?? null,
    };

    let resp: Response;
    try {
      resp = await fetch('/api/report-builder/v2/chat/stream', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        credentials: 'include',
        body: JSON.stringify(body),
        signal: controller.signal,
      });
    } catch (err) {
      if (controller.signal.aborted) {
        finalize({ status: 'interrupted', lastError: null });
        return;
      }
      logger.warn('sherlock streamTurn fetch failed', { err: String(err) });
      finalize({ status: 'error', lastError: 'Network error while streaming the turn.' });
      return;
    }

    if (!resp.ok || !resp.body) {
      finalize({
        status: 'error',
        lastError: `Server returned ${resp.status} starting the turn stream.`,
      });
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    try {
      while (!controller.signal.aborted) {
        const { value, done: streamDone } = await reader.read();
        if (streamDone) break;
        buffer += decoder.decode(value, { stream: true });
        let boundary = buffer.indexOf('\n\n');
        while (boundary >= 0) {
          const frame = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          handleFrame({
            frame,
            sessionId: options.sessionId,
            invalidateSnapshot,
            onTerminal: finalize,
          });
          boundary = buffer.indexOf('\n\n');
        }
      }
      if (!resolved) {
        if (controller.signal.aborted) {
          finalize({ status: 'interrupted', lastError: null });
        } else {
          finalize({
            status: 'error',
            lastError: 'Sherlock stopped responding mid-answer. Try sending your question again.',
          });
        }
      }
    } catch (err) {
      if (controller.signal.aborted) {
        finalize({ status: 'interrupted', lastError: null });
        return;
      }
      logger.warn('sherlock streamTurn read failed', { err: String(err) });
      finalize({ status: 'error', lastError: 'Lost connection to Sherlock. Refresh and try again.' });
    }
  })();

  void terminal;
  void rejectDone;
  return {
    abort() {
      controller.abort();
      if (!resolved) {
        finalize({ status: 'interrupted', lastError: null });
      }
    },
    done,
  };
}

interface HandleFrameArgs {
  frame: string;
  sessionId: string;
  invalidateSnapshot(): void;
  onTerminal(payload: TurnTerminal): void;
}

export function handleFrame({
  frame,
  sessionId,
  invalidateSnapshot,
  onTerminal,
}: HandleFrameArgs): void {
  let eventName = 'message';
  const dataLines: string[] = [];
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim());
    }
  }
  if (dataLines.length === 0) return;
  let payload: unknown;
  try {
    payload = JSON.parse(dataLines.join('\n'));
  } catch (err) {
    logger.warn('sherlock SSE: malformed JSON frame', { err: String(err), eventName });
    invalidateSnapshot();
    return;
  }

  if (eventName === 'turn_terminal') {
    const term = readTerminal(payload);
    if (term) onTerminal(term);
    return;
  }
  if (eventName === 'session') {
    // Session metadata frame — informational; nothing to apply.
    return;
  }
  if (eventName !== 'part_added' && eventName !== 'part_updated') {
    logger.debug('sherlock SSE: ignoring unknown event', { eventName });
    return;
  }
  if (!isPartFramePayload(payload)) {
    logger.warn('sherlock SSE: payload missing seq/part', { eventName });
    invalidateSnapshot();
    return;
  }
  if (!validateSherlockPart(payload.part)) {
    logger.warn('sherlock SSE: part failed ajv validation', {
      eventName,
      seq: payload.seq,
    });
    invalidateSnapshot();
    return;
  }
  const streamEvent: StreamEvent = {
    kind: eventName,
    seq: payload.seq,
    part: payload.part,
  };
  useStreamStore.getState().applyEvent(sessionId, streamEvent);
  if (useStreamStore.getState().hasGapBySession[sessionId]) {
    invalidateSnapshot();
  }
}

function isPartFramePayload(
  value: unknown,
): value is { seq: number; part: unknown } {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.seq === 'number' &&
    typeof v.part === 'object' &&
    v.part !== null
  );
}

function readTerminal(value: unknown): TurnTerminal | null {
  if (typeof value !== 'object' || value === null) return null;
  const v = value as Record<string, unknown>;
  const status =
    v.status === 'done' || v.status === 'error' || v.status === 'interrupted'
      ? (v.status as TerminalStatus)
      : null;
  if (!status) return null;
  const lastError = typeof v.lastError === 'string' ? v.lastError : null;
  return { status, lastError };
}
