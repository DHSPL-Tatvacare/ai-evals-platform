/**
 * Chip batcher — a single module-level queue that coalesces
 * `requestChip(filters, filtersKey, ownerType, ownerId)` calls into one batch POST
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
import type { ChipSummary, CostFilters, OwnerType } from '../types';

const WINDOW_MS = 50;
const MAX_BATCH = 100;

interface PendingEntry {
  filtersKey: string;
  filters: Pick<CostFilters, 'range' | 'appId' | 'provider' | 'model'>;
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

  for (const entries of byFiltersKey.values()) {
    const filters = entries[0]?.filters ?? { range: '7d' };

    for (let i = 0; i < entries.length; i += MAX_BATCH) {
      const slice = entries.slice(i, i + MAX_BATCH);
      try {
        const response = await costApi.batchChips(
          filters,
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
  filters: Pick<CostFilters, 'range' | 'appId' | 'provider' | 'model'>,
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
      filters,
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
  const filters = useCostStore((s) => s.filters);
  const filtersKey = useCostStore((s) => s.filtersKey);
  const activeKey = ownerType && ownerId ? keyOf(filtersKey, ownerType, ownerId) : null;
  // Initializing state from the cache avoids calling setState inside
  // `useEffect` for the hot path where the value is already memoized.
  const [resolved, setResolved] = useState<{ key: string; summary: ChipSummary } | null>(() => {
    if (!activeKey) return null;
    const cached = initialSummary(filtersKey, ownerType, ownerId);
    return cached ? { key: activeKey, summary: cached } : null;
  });
  const summary = initialSummary(filtersKey, ownerType, ownerId) ??
    (activeKey && resolved?.key === activeKey ? resolved.summary : null);
  const cancelledRef = useRef(false);

  useEffect(() => {
    cancelledRef.current = false;
    if (!ownerType || !ownerId || !activeKey) {
      return;
    }
    const cached = cache.get(activeKey);
    if (cached) {
      return;
    }
    void requestChip(filters, filtersKey, ownerType, ownerId).then((value) => {
      if (cancelledRef.current) return;
      setResolved({ key: activeKey, summary: value });
    });
    return () => {
      cancelledRef.current = true;
    };
  }, [activeKey, filters, filtersKey, ownerType, ownerId]);

  return { summary, loading: activeKey !== null && summary === null };
}
