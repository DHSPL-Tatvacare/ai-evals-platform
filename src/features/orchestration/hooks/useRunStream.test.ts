import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/services/api/orchestration', () => ({
  getRunOverlaySnapshot: vi.fn(async () => ({
    run: { status: 'running', error: undefined },
    nodeSteps: [],
  })),
}));

vi.mock('@/services/logger', () => ({
  logger: { warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

const refreshToken = vi.fn();
let currentToken: string | null = 'stale-token';

vi.mock('@/stores/authStore', () => ({
  useAuthStore: {
    getState: () => ({
      get accessToken() {
        return currentToken;
      },
      refreshToken,
    }),
  },
}));

import { useRunOverlayStore } from '@/features/orchestration/store/runOverlayStore';
import { useRunStream } from './useRunStream';

// A never-ending readable body so the fetch resolves "open" without the pump
// loop completing — lets the test assert the connect path deterministically.
function openBody(): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start() {
      // intentionally never enqueue/close
    },
  });
}

function authFailure(): Response {
  return { ok: false, status: 401, body: null } as unknown as Response;
}

function openResponse(): Response {
  return { ok: true, status: 200, body: openBody() } as unknown as Response;
}

const flush = () => new Promise((r) => setTimeout(r, 0));

describe('useRunStream 401 refresh-and-retry', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    currentToken = 'stale-token';
    useRunOverlayStore.getState().reset();
    useRunOverlayStore.getState().activateRun('run-401');
    useRunOverlayStore.getState().applyEvent('run-401', { type: 'run.started' });
    fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    useRunOverlayStore.getState().reset();
  });

  it('refreshes the token and reconnects with the fresh token on a 401', async () => {
    refreshToken.mockImplementation(async () => {
      currentToken = 'fresh-token';
      return true;
    });
    fetchSpy
      .mockResolvedValueOnce(authFailure())
      .mockResolvedValueOnce(openResponse());

    const { unmount } = renderHook(() => useRunStream('run-401'));
    await flush();
    await flush();
    await flush();

    expect(refreshToken).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledTimes(2);

    const secondCall = fetchSpy.mock.calls[1];
    const secondHeaders = (secondCall[1] as RequestInit).headers as Record<string, string>;
    expect(secondHeaders.Authorization).toBe('Bearer fresh-token');

    unmount();
  });

  it('never places the token in the URL or query string', async () => {
    refreshToken.mockImplementation(async () => {
      currentToken = 'fresh-token';
      return true;
    });
    fetchSpy
      .mockResolvedValueOnce(authFailure())
      .mockResolvedValueOnce(openResponse());

    const { unmount } = renderHook(() => useRunStream('run-401'));
    await flush();
    await flush();
    await flush();

    for (const call of fetchSpy.mock.calls) {
      const url = String(call[0]);
      expect(url).not.toContain('stale-token');
      expect(url).not.toContain('fresh-token');
      expect(url).not.toContain('token=');
      expect(url).not.toContain('access_token=');
    }

    unmount();
  });

  it('does NOT retry a second time if refresh fails', async () => {
    refreshToken.mockResolvedValue(false);
    fetchSpy.mockResolvedValueOnce(authFailure());

    const { unmount } = renderHook(() => useRunStream('run-401'));
    await flush();
    await flush();

    expect(refreshToken).toHaveBeenCalledTimes(1);
    // One auth-failed connect; no fresh-token retry connect.
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    unmount();
  });
});
