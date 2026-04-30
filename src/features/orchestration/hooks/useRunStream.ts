import { useEffect } from 'react';

import { useAuthStore } from '@/stores/authStore';
import { useRunOverlayStore } from '@/features/orchestration/store/runOverlayStore';
import { logger } from '@/services/logger';

/**
 * Subscribe to /api/orchestration/runs/:id/stream while the consumer is
 * mounted; tear down on unmount.
 *
 * Why fetch + ReadableStream rather than EventSource: EventSource cannot
 * carry a Bearer header (browser API gap), and our auth model is
 * Authorization-header-only — cookies are not the source of truth. The SSE
 * wire format is just `event:` + `data:` lines, easy enough to parse here.
 */
export function useRunStream(runId: string | undefined): void {
  useEffect(() => {
    if (!runId) return;
    const token = useAuthStore.getState().accessToken;
    if (!token) return;

    useRunOverlayStore.getState().reset();
    useRunOverlayStore.getState().setStreamStatus('connecting');

    const abort = new AbortController();
    let cancelled = false;

    const pump = async () => {
      try {
        const resp = await fetch(`/api/orchestration/runs/${runId}/stream`, {
          method: 'GET',
          headers: { Authorization: `Bearer ${token}` },
          credentials: 'include',
          signal: abort.signal,
        });
        if (!resp.ok || !resp.body) {
          useRunOverlayStore.getState().setStreamStatus('error');
          return;
        }
        useRunOverlayStore.getState().setStreamStatus('open');

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (!cancelled) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          let boundary = buffer.indexOf('\n\n');
          while (boundary >= 0) {
            const frame = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);

            let eventType = 'message';
            const dataLines: string[] = [];
            for (const line of frame.split('\n')) {
              if (line.startsWith('event:')) eventType = line.slice(6).trim();
              else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
            }

            if (dataLines.length > 0) {
              try {
                const data = JSON.parse(dataLines.join('\n'));
                useRunOverlayStore.getState().applyEvent({ ...data, type: eventType });
              } catch (err) {
                logger.warn('useRunStream: malformed SSE frame', { err: String(err) });
              }
            }
            boundary = buffer.indexOf('\n\n');
          }
        }
        useRunOverlayStore.getState().setStreamStatus('closed');
      } catch (err) {
        if (cancelled) return;
        logger.warn('useRunStream: stream failed', { err: String(err) });
        useRunOverlayStore.getState().setStreamStatus('error');
      }
    };

    void pump();

    return () => {
      cancelled = true;
      abort.abort();
      useRunOverlayStore.getState().setStreamStatus('closed');
    };
  }, [runId]);
}
