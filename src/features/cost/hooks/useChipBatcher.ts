/**
 * Chip batcher — a single module-level queue that coalesces
 * `requestChip(filtersKey, ownerType, ownerId)` calls into one batch POST
 * per 50 ms window (or sooner if the queue hits 100 items).
 *
 * Contract (§10.8):
 *   - N chips under one filtersKey → ceil(N / 100) batch calls.
 *   - Same key re-requested while in-flight → no duplicate request.
 *   - Cached key → zero network.
 *   - Rendering the same list again with same filtersKey → zero network.
 */
import { useEffect, useRef, useState } from 'react';
import { costApi } from '@/services/api/costApi';
import { useCostStore } from '@/stores/costStore';
import type { ChipSummary, OwnerType } from '../types';

const WINDOW_MS = 50;
const MAX_BATCH = 100;

interface PendingEntry {
  filtersKey: string;
  ownerType: OwnerType;
  ownerId: string;
  resolvers: Array<(value: ChipSummary) => void>;
}

const cache = new Map<string, ChipSummary>();
const pending = new Map<string, PendingEntry>();
let flushTimer: number | null = null;

const EMPTY: ChipSummary = { costUsd: 0, totalTokens: 0, callCount: 0 };

function keyOf(filtersKey: string, ownerType: OwnerType, ownerId: string): string {
  return `${filtersKey}:${ownerType}:${ownerId}`;
}

function scheduleFlush() {
  if (flushTimer !== null) return;
  flushTimer = window.setTimeout(flush, WINDOW_MS);
}

async function flush() {
  flushTimer = null;
  if (pending.size === 0) return;

  const byFiltersKey = new Map<string, PendingEntry[]>();
  for (const entry of pending.values()) {
    const bucket = byFiltersKey.get(entry.filtersKey) ?? [];
    bucket.push(entry);
    byFiltersKey.set(entry.filtersKey, bucket);
  }
  pending.clear();

  const resolveEntry = (entry: PendingEntry, summary: ChipSummary) => {
    cache.set(keyOf(entry.filtersKey, entry.ownerType, entry.ownerId), summary);
    for (const resolve of entry.resolvers) resolve(summary);
  };

  for (const [filtersKey, entries] of byFiltersKey) {
    // filtersKey is produced by `hashFilters`: `range|appId|provider|model`.
    const [range, appId] = filtersKey.split('|');

    for (let i = 0; i < entries.length; i += MAX_BATCH) {
      const slice = entries.slice(i, i + MAX_BATCH);
      try {
        const response = await costApi.batchChips(
          { range: range || '7d', appId: appId || undefined },
          slice.map((e) => ({ ownerType: e.ownerType, ownerId: e.ownerId })),
        );
        for (const entry of slice) {
          const summary = response[`${entry.ownerType}:${entry.ownerId}`] ?? EMPTY;
          resolveEntry(entry, summary);
        }
      } catch {
        for (const entry of slice) resolveEntry(entry, EMPTY);
      }
    }
  }
}

export function requestChip(
  filtersKey: string,
  ownerType: OwnerType,
  ownerId: string,
): Promise<ChipSummary> {
  const key = keyOf(filtersKey, ownerType, ownerId);
  const cached = cache.get(key);
  if (cached) return Promise.resolve(cached);

  const existing = pending.get(key);
  if (existing) {
    return new Promise<ChipSummary>((resolve) => existing.resolvers.push(resolve));
  }

  return new Promise<ChipSummary>((resolve) => {
    pending.set(key, {
      filtersKey,
      ownerType,
      ownerId,
      resolvers: [resolve],
    });
    if (pending.size >= MAX_BATCH) {
      if (flushTimer !== null) {
        window.clearTimeout(flushTimer);
        flushTimer = null;
      }
      void flush();
    } else {
      scheduleFlush();
    }
  });
}

export function clearChipCache(): void {
  cache.clear();
}

/**
 * Hook form: returns { summary, loading }. Callers that want absence to be
 * indistinguishable from loading can render nothing while loading is true.
 */
function initialSummary(
  filtersKey: string,
  ownerType: OwnerType | null | undefined,
  ownerId: string | null | undefined,
): ChipSummary | null {
  if (!ownerType || !ownerId) return null;
  return cache.get(keyOf(filtersKey, ownerType, ownerId)) ?? null;
}

export function useChipSummary(
  ownerType: OwnerType | null | undefined,
  ownerId: string | null | undefined,
): { summary: ChipSummary | null; loading: boolean } {
  const filtersKey = useCostStore((s) => s.filtersKey);
  // Initializing state from the cache avoids calling setState inside
  // `useEffect` for the hot path where the value is already memoized.
  const [summary, setSummary] = useState<ChipSummary | null>(() =>
    initialSummary(filtersKey, ownerType, ownerId),
  );
  const [loading, setLoading] = useState<boolean>(() =>
    initialSummary(filtersKey, ownerType, ownerId) === null && !!ownerType && !!ownerId,
  );
  const cancelledRef = useRef(false);

  useEffect(() => {
    cancelledRef.current = false;
    if (!ownerType || !ownerId) {
      return;
    }
    const cached = cache.get(keyOf(filtersKey, ownerType, ownerId));
    if (cached) {
      return;
    }
    void requestChip(filtersKey, ownerType, ownerId).then((value) => {
      if (cancelledRef.current) return;
      setSummary(value);
      setLoading(false);
    });
    return () => {
      cancelledRef.current = true;
    };
  }, [filtersKey, ownerType, ownerId]);

  return { summary, loading };
}
