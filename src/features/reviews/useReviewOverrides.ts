import { useEffect, useMemo } from 'react';
import type { InlineEditState } from '@/features/reviews/inline/types';
import type { ReviewItemRecord } from '@/types/reviews';
import { useReviewModeStore } from '@/stores/reviewModeStore';
import { useReviewOverridesStore } from './reviewOverridesStore';
import { reviewEditKey } from './keys';

export interface ReviewOverride {
  itemKey: string;
  attributeKey: string;
  originalValue: string | null;
  reviewedValue: string;
  note: string | null;
  source: 'live' | 'persisted';
}

interface UseReviewOverridesResult {
  /** Lookup a single override by itemKey + attributeKey. Stable identity across renders. */
  getOverride: (itemKey: string, attributeKey: string) => ReviewOverride | null;
  /** All overrides (live during edit, persisted otherwise). Only `decision='correct'` entries. */
  overrides: ReviewOverride[];
}

const EMPTY_OVERRIDES: ReviewOverride[] = [];

/**
 * Unified accessor for human-review overrides on a run.
 *
 * Returns overrides from the active review draft (live) when the user is editing
 * this run, falling back to the run's latest finalized review otherwise. Callers
 * pass the item key exactly as the backend stores it (e.g. `thread:thrd-xxx`,
 * `call:xxx`, `segment:123`, `field:foo`) and the attribute key (e.g. `severity`,
 * `rule:apply_user_corrections`, `overall_verdict`).
 *
 * Only `decision === 'correct'` entries with a non-null `reviewedValue` are
 * treated as overrides. `accept` (endorsement of AI verdict) yields `null`.
 *
 * Persisted items are fetched through `reviewOverridesStore`, so every consumer
 * on the same page shares a single network request.
 */
export function useReviewOverrides(runId?: string): UseReviewOverridesResult {
  const storeRunId = useReviewModeStore((s) => s.runId);
  const storeActive = useReviewModeStore((s) => s.active);
  const storeStatus = useReviewModeStore((s) => s.status);
  const liveEdits = useReviewModeStore((s) => s.edits);

  const isLive = !!runId
    && storeActive
    && storeRunId === runId
    && (storeStatus === 'reviewing' || storeStatus === 'saving');

  // Subscribe to this run's cache entry; `items` defaults to an empty array
  // so consumers render cleanly while the fetch is in flight.
  const persistedItems = useReviewOverridesStore(
    (s) => (runId ? s.entries[runId]?.items : undefined) ?? (EMPTY_OVERRIDES as unknown as ReviewItemRecord[]),
  );
  const ensureLoaded = useReviewOverridesStore((s) => s.ensureLoaded);

  useEffect(() => {
    if (!runId || isLive) return;
    ensureLoaded(runId);
  }, [runId, isLive, ensureLoaded]);

  // Build an O(1) lookup index for the current data snapshot. Memoized on the
  // same deps that drive overrides, so the getOverride identity only changes
  // when the underlying data changes — not on every render.
  const lookup = useMemo(() => {
    const index = new Map<string, { originalValue: string | null; reviewedValue: string; note: string | null; source: 'live' | 'persisted' }>();
    if (isLive) {
      for (const [key, edit] of Object.entries(liveEdits) as Array<[string, InlineEditState]>) {
        if (edit.decision !== 'correct' || !edit.reviewedValue) continue;
        index.set(key, {
          originalValue: edit.originalValue,
          reviewedValue: edit.reviewedValue,
          note: edit.note ?? null,
          source: 'live',
        });
      }
    } else {
      for (const item of persistedItems) {
        if (item.decision !== 'correct' || !item.reviewedValue) continue;
        index.set(reviewEditKey(item.itemKey, item.attributeKey), {
          originalValue: item.originalValue,
          reviewedValue: item.reviewedValue,
          note: item.note,
          source: 'persisted',
        });
      }
    }
    return index;
  }, [isLive, liveEdits, persistedItems]);

  const getOverride = useMemo(() => (
    (itemKey: string, attributeKey: string): ReviewOverride | null => {
      const hit = lookup.get(reviewEditKey(itemKey, attributeKey));
      if (!hit) return null;
      return {
        itemKey,
        attributeKey,
        originalValue: hit.originalValue,
        reviewedValue: hit.reviewedValue,
        note: hit.note,
        source: hit.source,
      };
    }
  ), [lookup]);

  const overrides = useMemo<ReviewOverride[]>(() => {
    if (isLive) {
      const list: ReviewOverride[] = [];
      for (const [key, edit] of Object.entries(liveEdits)) {
        if (edit.decision !== 'correct' || !edit.reviewedValue) continue;
        const sepIdx = key.indexOf('::');
        if (sepIdx < 0) continue;
        list.push({
          itemKey: key.slice(0, sepIdx),
          attributeKey: key.slice(sepIdx + 2),
          originalValue: edit.originalValue,
          reviewedValue: edit.reviewedValue,
          note: edit.note ?? null,
          source: 'live',
        });
      }
      return list.length > 0 ? list : EMPTY_OVERRIDES;
    }
    if (persistedItems.length === 0) return EMPTY_OVERRIDES;
    const list: ReviewOverride[] = [];
    for (const item of persistedItems) {
      if (item.decision !== 'correct' || !item.reviewedValue) continue;
      list.push({
        itemKey: item.itemKey,
        attributeKey: item.attributeKey,
        originalValue: item.originalValue,
        reviewedValue: item.reviewedValue,
        note: item.note,
        source: 'persisted',
      });
    }
    return list.length > 0 ? list : EMPTY_OVERRIDES;
  }, [isLive, liveEdits, persistedItems]);

  return { getOverride, overrides };
}
