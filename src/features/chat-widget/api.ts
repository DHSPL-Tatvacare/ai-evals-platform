/**
 * Chat-widget HTTP surface (post Phase 2 Step C cutover).
 *
 * The SSE stream now lives in `features/sherlock/sse.ts` (typed Part wire).
 * This module only retains the two non-stream endpoints the widget still
 * needs: the session snapshot fetch (for active-turn discovery on
 * `selectSession`) and the per-turn cancel.
 */
import { apiRequest } from '@/services/api/client';

import type { BuilderSessionData } from './types';

interface CancelTurnResponse {
  sessionId: string;
  turnId: string;
  result: 'cancelled' | 'forced_interrupted' | 'already_terminal';
  turnStatus: string;
  message: string;
}

export async function getBuilderSession(
  appId: string,
  sessionId: string,
): Promise<BuilderSessionData> {
  return apiRequest<BuilderSessionData>(
    `/api/report-builder/v2/sessions/${sessionId}?app_id=${encodeURIComponent(appId)}`,
  );
}

export async function cancelChatTurn(
  appId: string,
  sessionId: string,
  turnId: string,
): Promise<CancelTurnResponse> {
  return apiRequest<CancelTurnResponse>(
    `/api/report-builder/v2/sessions/${encodeURIComponent(sessionId)}/turns/${encodeURIComponent(turnId)}/cancel?app_id=${encodeURIComponent(appId)}`,
    { method: 'POST' },
  );
}
