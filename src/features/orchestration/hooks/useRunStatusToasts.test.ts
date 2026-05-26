import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/services/notifications', () => ({
  notificationService: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

import { notificationService } from '@/services/notifications';
import { useRunOverlayStore } from '@/features/orchestration/store/runOverlayStore';
import { useRunStatusToasts } from './useRunStatusToasts';

// Access the module-level toasted-set so tests can reset it between cases.
// The hook exports a `_resetToastedForTest` helper for exactly this purpose.
import { _resetToastedForTest } from './useRunStatusToasts';

describe('useRunStatusToasts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useRunOverlayStore.getState().reset();
    _resetToastedForTest();
  });

  afterEach(() => {
    _resetToastedForTest();
  });

  it('fires a success toast once when run transitions to completed', () => {
    useRunOverlayStore.getState().activateRun('run-abc');
    useRunOverlayStore.getState().applyEvent('run-abc', { type: 'run.started' });

    const { rerender } = renderHook(() => useRunStatusToasts('run-abc'));

    act(() => {
      useRunOverlayStore.getState().applyEvent('run-abc', { type: 'run.completed' });
    });

    rerender();

    expect(notificationService.success).toHaveBeenCalledTimes(1);
    expect(notificationService.success).toHaveBeenCalledWith(
      expect.stringContaining('run-abc'.slice(0, 8)),
    );
  });

  it('does NOT fire a second toast when the overlay is re-opened for the same run', () => {
    useRunOverlayStore.getState().activateRun('run-abc');
    useRunOverlayStore.getState().applyEvent('run-abc', { type: 'run.started' });

    const { rerender, unmount } = renderHook(() => useRunStatusToasts('run-abc'));

    act(() => {
      useRunOverlayStore.getState().applyEvent('run-abc', { type: 'run.completed' });
    });
    rerender();

    expect(notificationService.success).toHaveBeenCalledTimes(1);

    // Simulate overlay close + re-open: unmount, reset store to same terminal
    // state (as if SSE replayed), remount with same runId.
    unmount();
    useRunOverlayStore.getState().reset();
    useRunOverlayStore.getState().activateRun('run-abc');
    useRunOverlayStore.getState().applyEvent('run-abc', { type: 'run.completed' });

    renderHook(() => useRunStatusToasts('run-abc'));

    // The module-level dedup set prevents a second toast.
    expect(notificationService.success).toHaveBeenCalledTimes(1);
  });

  it('fires an error toast for a failed run with the error string', () => {
    useRunOverlayStore.getState().activateRun('run-xyz');
    useRunOverlayStore.getState().applyEvent('run-xyz', { type: 'run.started' });

    const { rerender } = renderHook(() => useRunStatusToasts('run-xyz'));

    act(() => {
      useRunOverlayStore.getState().applyEvent('run-xyz', {
        type: 'run.failed',
        error: 'timeout',
      });
    });

    rerender();

    expect(notificationService.error).toHaveBeenCalledTimes(1);
    expect(notificationService.error).toHaveBeenCalledWith(
      expect.stringContaining('timeout'),
    );
  });

  it('does NOT fire again for the same failed run on overlay re-open', () => {
    useRunOverlayStore.getState().activateRun('run-xyz');
    useRunOverlayStore.getState().applyEvent('run-xyz', { type: 'run.started' });

    const { rerender, unmount } = renderHook(() => useRunStatusToasts('run-xyz'));

    act(() => {
      useRunOverlayStore.getState().applyEvent('run-xyz', {
        type: 'run.failed',
        error: 'timeout',
      });
    });
    rerender();

    expect(notificationService.error).toHaveBeenCalledTimes(1);

    unmount();
    useRunOverlayStore.getState().reset();
    useRunOverlayStore.getState().activateRun('run-xyz');
    useRunOverlayStore.getState().applyEvent('run-xyz', {
      type: 'run.failed',
      error: 'timeout',
    });

    renderHook(() => useRunStatusToasts('run-xyz'));

    expect(notificationService.error).toHaveBeenCalledTimes(1);
  });

  it('does not toast when the first observed status is already terminal', () => {
    // Inspector-open hydration: store settles on a terminal status BEFORE the
    // hook mounts, so the hook's first observation is terminal (no transition).
    useRunOverlayStore.getState().activateRun('run-hydrated');
    useRunOverlayStore.getState().applyEvent('run-hydrated', { type: 'run.completed' });

    renderHook(() => useRunStatusToasts('run-hydrated'));

    expect(notificationService.success).not.toHaveBeenCalled();
  });

  it('toasts once on a running -> completed transition', () => {
    useRunOverlayStore.getState().activateRun('run-trans');
    useRunOverlayStore.getState().applyEvent('run-trans', { type: 'run.started' });

    const { rerender } = renderHook(() => useRunStatusToasts('run-trans'));

    act(() => {
      useRunOverlayStore.getState().applyEvent('run-trans', { type: 'run.completed' });
    });
    rerender();

    expect(notificationService.success).toHaveBeenCalledTimes(1);
  });

  it('does NOT fire for cancelled runs', () => {
    useRunOverlayStore.getState().activateRun('run-can');
    useRunOverlayStore.getState().applyEvent('run-can', { type: 'run.started' });

    const { rerender } = renderHook(() => useRunStatusToasts('run-can'));

    act(() => {
      useRunOverlayStore.getState().applyEvent('run-can', { type: 'run.cancelled' });
    });

    rerender();

    expect(notificationService.success).not.toHaveBeenCalled();
    expect(notificationService.error).not.toHaveBeenCalled();
  });

  it('fires independently for a second distinct run', () => {
    // First run.
    useRunOverlayStore.getState().activateRun('run-1');
    useRunOverlayStore.getState().applyEvent('run-1', { type: 'run.started' });

    const { rerender, unmount } = renderHook(() => useRunStatusToasts('run-1'));

    act(() => {
      useRunOverlayStore.getState().applyEvent('run-1', { type: 'run.completed' });
    });
    rerender();
    expect(notificationService.success).toHaveBeenCalledTimes(1);

    // Switch overlay to a second, different run.
    unmount();
    useRunOverlayStore.getState().reset();
    useRunOverlayStore.getState().activateRun('run-2');
    useRunOverlayStore.getState().applyEvent('run-2', { type: 'run.started' });

    const hook2 = renderHook(() => useRunStatusToasts('run-2'));

    act(() => {
      useRunOverlayStore.getState().applyEvent('run-2', { type: 'run.completed' });
    });
    hook2.rerender();

    // Second run gets its own toast.
    expect(notificationService.success).toHaveBeenCalledTimes(2);
  });
});
