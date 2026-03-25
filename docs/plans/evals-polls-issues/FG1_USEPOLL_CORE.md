# FG-1: Core Polling Resilience

## Files

- `src/hooks/usePoll.ts`
- `src/services/api/jobPolling.ts`

## Fix 1: Error backoff in `usePoll` (Bug #2)

### Problem
`usePoll.ts:32-33` catches all errors and returns `{ done: false }`, meaning polling continues at full speed even when every request fails. If the API goes down, the frontend hammers it every 5s with no feedback.

### Solution
Add an error counter ref inside the `poll()` call wrapper. On consecutive errors, apply exponential backoff by sleeping an additional delay before the next attempt. Cap at 60s. Reset the counter on any successful call.

### Implementation

In `src/hooks/usePoll.ts`, change the `poll()` call's `fn` to:

```typescript
export function usePoll({ fn, enabled, intervalMs = 5000 }: UsePollOptions): void {
  const fnRef = useRef(fn);
  useEffect(() => { fnRef.current = fn; });

  useEffect(() => {
    if (!enabled) return;

    const controller = new AbortController();
    let consecutiveErrors = 0;

    poll<void>({
      fn: async () => {
        try {
          const keepGoing = await fnRef.current();
          consecutiveErrors = 0; // reset on success
          return { done: !keepGoing };
        } catch {
          consecutiveErrors++;
          return { done: false }; // keep polling, but poll() will sleep intervalMs naturally
        }
      },
      intervalMs,
      // Pass a dynamic delay adder for backoff
      getBackoffMs: () => {
        if (consecutiveErrors <= 1) return 0;
        // Exponential: 5s, 10s, 20s, 40s, capped at 60s
        return Math.min(intervalMs * 2 ** (consecutiveErrors - 1), 60000);
      },
      signal: controller.signal,
    }).catch(() => {
      // AbortError on unmount — expected
    });

    return () => controller.abort();
  }, [enabled, intervalMs]);
}
```

This requires adding `getBackoffMs` support to `poll()` in `jobPolling.ts`.

### Changes to `poll()` in `jobPolling.ts`

Add optional `getBackoffMs` to `PollConfig`:

```typescript
export interface PollConfig<T> {
  fn: () => Promise<{ done: boolean; data?: T }>;
  intervalMs?: number;
  signal?: AbortSignal;
  /** Optional dynamic backoff. Called before each sleep. Added to intervalMs. */
  getBackoffMs?: () => number;
}
```

In the `poll()` function, after `const result = await fn();` and before the sleep, compute the actual delay:

```typescript
// Current (line 86-103):
await new Promise<void>((resolve, reject) => { ... setTimeout(..., intervalMs) ... });

// Changed to:
const sleepMs = intervalMs + (config.getBackoffMs?.() ?? 0);
await new Promise<void>((resolve, reject) => { ... setTimeout(..., sleepMs) ... });
```

This is the only change to `poll()`. The function signature stays backward-compatible (new param is optional).

---

## Fix 2: Visibility listener leak (Bug #8)

### Problem
`jobPolling.ts:60-76` — When the tab is hidden and the signal is already aborted at the moment we enter the `if (document.hidden)` block, the `abort` event listener we add on line 70 won't fire (event already dispatched), leaving an orphaned `visibilitychange` listener.

### Solution
Check `signal.aborted` BEFORE entering the visibility wait block, and also check it INSIDE the promise before setting up listeners.

### Implementation

Replace lines 60-76 in `jobPolling.ts`:

```typescript
// Pause when tab is hidden
if (typeof document !== 'undefined' && document.hidden) {
  // Check abort BEFORE setting up listeners
  if (signal?.aborted) {
    throw new DOMException('Polling aborted', 'AbortError');
  }

  await new Promise<void>((resolve) => {
    const onVisible = () => {
      if (!document.hidden) {
        document.removeEventListener('visibilitychange', onVisible);
        resolve();
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    if (signal) {
      // Handle case where signal aborts while we're waiting
      if (signal.aborted) {
        document.removeEventListener('visibilitychange', onVisible);
        resolve();
        return;
      }
      signal.addEventListener('abort', () => {
        document.removeEventListener('visibilitychange', onVisible);
        resolve();
      }, { once: true });
    }
  });
}
```

The key change: check `signal.aborted` both before and inside the promise constructor to handle the race window. The existing `signal?.aborted` check on line 78 remains as a secondary guard.

---

## Testing

1. Open the app with backend running → navigate to RunList with a running job → confirm polling works normally (5s intervals)
2. Stop the backend (docker compose stop backend) → confirm polling slows down (check Network tab: intervals increase from 5s → 10s → 20s → ..., capping at ~65s)
3. Restart backend → confirm polling recovers to 5s immediately on next success
4. With a running job visible, switch to another tab → switch back → confirm polling resumes without leaked listeners (no console errors)
