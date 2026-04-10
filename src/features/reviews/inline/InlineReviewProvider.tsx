import { createContext, useContext, useMemo } from 'react';
import type { ReactNode } from 'react';
import type { AppId } from '@/types';
import { useAppConfig } from '@/hooks/useCurrentAppData';
import { useReviewModeStore } from '@/stores/reviewModeStore';
import type { InlineReviewContextValue } from './types';

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const InlineReviewContext = createContext<InlineReviewContextValue | null>(null);

export function useInlineReview(): InlineReviewContextValue {
  const value = useContext(InlineReviewContext);
  if (!value) {
    throw new Error('useInlineReview must be used within an InlineReviewProvider');
  }
  return value;
}

export function useInlineReviewOptional(): InlineReviewContextValue | null {
  return useContext(InlineReviewContext);
}

// ---------------------------------------------------------------------------
// Provider (compatibility shim — delegates to reviewModeStore)
// ---------------------------------------------------------------------------

interface InlineReviewProviderProps {
  runId: string;
  appId: AppId;
  enabled: boolean;
  children: ReactNode;
}

export function InlineReviewProvider({ runId, appId, enabled, children }: InlineReviewProviderProps) {
  const appConfig = useAppConfig(appId);
  const reviewEnabled = enabled && appConfig.features.hasReviews && appConfig.reviews.enabled;

  const store = useReviewModeStore();

  const value = useMemo<InlineReviewContextValue>(() => {
    const isEditing =
      store.active &&
      store.runId === runId &&
      (store.status === 'reviewing' || store.status === 'saving');

    const dirty = store.getDirty();

    // Build a minimal selectedReview stub when the store has an active review
    // for this run. Many consumers only check `selectedReview?.status === 'draft'`
    // or null.
    const selectedReview =
      store.active && store.runId === runId && store.reviewId
        ? {
            id: store.reviewId,
            runId,
            reviewerUserId: '',
            reviewerName: null,
            status: 'draft' as const,
            overallDecision: null,
            notes: store.notes,
            reviewSnapshot: {},
            createdAt: '',
            updatedAt: '',
            completedAt: null,
            items: [],
          }
        : null;

    return {
      appId,
      isEditing,
      hasDirtyChanges: dirty.isDirty,
      loading: store.status === 'entering',
      saving: store.status === 'saving' || store.status === 'finalizing',
      context: store.active && store.runId === runId ? store.context : null,
      selectedReview,
      edits: store.active && store.runId === runId ? store.edits : {},
      dirtyCount: dirty.dirtyCount,
      dirtySummary: dirty.dirtySummary,

      startDraft: () => store.enterReview(runId, appId),

      getEdit: (itemKey, attributeKey) => store.getEdit(itemKey, attributeKey),

      updateAttribute: (item, attribute, patch) =>
        store.updateAttribute(item.itemKey, attribute.key, {
          ...patch,
          itemKey: item.itemKey,
          itemType: item.itemType,
          attributeKey: attribute.key,
          originalValue: attribute.originalValue,
        }),

      acceptAttribute: (item, attribute) => store.acceptAttribute(item, attribute),

      clearAttribute: (item, attribute) => store.clearAttribute(item, attribute),

      correctAttribute: (item, attribute, reviewedValue) =>
        store.correctAttribute(item, attribute, reviewedValue),

      setAttributeNote: (item, attribute, note) =>
        store.setAttributeNote(item, attribute, note),

      saveDraft: () => store.saveDraft(),

      finalize: () => store.finalize(),

      discardDraft: () => store.discardDraft(),
    };
  }, [
    appId,
    runId,
    store,
  ]);

  if (!reviewEnabled) {
    return <>{children}</>;
  }

  return (
    <InlineReviewContext.Provider value={value}>
      {children}
    </InlineReviewContext.Provider>
  );
}
