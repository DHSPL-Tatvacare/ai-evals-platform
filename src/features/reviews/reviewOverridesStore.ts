import { create } from 'zustand';
import type { ReviewItemRecord } from '@/types/reviews';
import { fetchRunReviewContext, fetchReviewDetail } from '@/services/api/reviewsApi';

/**
 * Shared cache of persisted review items per runId.
 *
 * Every surface that needs to read a run's finalized review goes through this
 * store, so we fetch once per runId regardless of how many components mount.
 *
 * Mutations (finalize / discard) must call `invalidate(runId)` so the next
 * read re-fetches; `reviewModeStore` does this.
 */

type EntryStatus = 'idle' | 'loading' | 'loaded' | 'error';

interface Entry {
  status: EntryStatus;
  items: ReviewItemRecord[];
  promise: Promise<ReviewItemRecord[]> | null;
}

interface ReviewOverridesStoreState {
  entries: Record<string, Entry>;
  /**
   * Trigger a fetch for `runId` if one is not already in flight or cached.
   * Returns the items array once the fetch settles.
   */
  ensureLoaded: (runId: string) => Promise<ReviewItemRecord[]>;
  /** Drop the cache for `runId`. Next `ensureLoaded` will re-fetch. */
  invalidate: (runId: string) => void;
}

const EMPTY_ITEMS: ReviewItemRecord[] = [];

export const useReviewOverridesStore = create<ReviewOverridesStoreState>((set, get) => ({
  entries: {},

  ensureLoaded: (runId) => {
    const existing = get().entries[runId];
    if (existing?.status === 'loaded') {
      return Promise.resolve(existing.items);
    }
    if (existing?.promise) {
      return existing.promise;
    }

    const promise: Promise<ReviewItemRecord[]> = (async () => {
      try {
        const ctx = await fetchRunReviewContext(runId);
        const reviewId = ctx.latestReviewId ?? ctx.draftReviewId;
        let items: ReviewItemRecord[] = [];
        if (reviewId) {
          const detail = await fetchReviewDetail(reviewId);
          items = detail.items;
        }
        set((state) => ({
          entries: {
            ...state.entries,
            [runId]: { status: 'loaded', items, promise: null },
          },
        }));
        return items;
      } catch {
        set((state) => ({
          entries: {
            ...state.entries,
            [runId]: { status: 'error', items: EMPTY_ITEMS, promise: null },
          },
        }));
        return EMPTY_ITEMS;
      }
    })();

    set((state) => ({
      entries: {
        ...state.entries,
        [runId]: {
          status: 'loading',
          items: existing?.items ?? EMPTY_ITEMS,
          promise,
        },
      },
    }));

    return promise;
  },

  invalidate: (runId) => {
    set((state) => {
      if (!state.entries[runId]) return state;
      const next = { ...state.entries };
      delete next[runId];
      return { entries: next };
    });
  },
}));

/** Read-only selector for a run's persisted items (empty array if not loaded). */
export function selectPersistedItems(runId: string | undefined): ReviewItemRecord[] {
  if (!runId) return EMPTY_ITEMS;
  return useReviewOverridesStore.getState().entries[runId]?.items ?? EMPTY_ITEMS;
}
