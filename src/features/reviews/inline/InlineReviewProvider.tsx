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

  // Subscribe to individual slices to avoid full-store re-renders
  const active = useReviewModeStore((s) => s.active);
  const storeRunId = useReviewModeStore((s) => s.runId);
  const status = useReviewModeStore((s) => s.status);
  const reviewId = useReviewModeStore((s) => s.reviewId);
  const notes = useReviewModeStore((s) => s.notes);
  const context = useReviewModeStore((s) => s.context);
  const edits = useReviewModeStore((s) => s.edits);

  // Actions are stable references — read once from getState
  const actions = useMemo(() => {
    const s = useReviewModeStore.getState();
    return {
      enterReview: s.enterReview,
      updateAttribute: s.updateAttribute,
      acceptAttribute: s.acceptAttribute,
      correctAttribute: s.correctAttribute,
      clearAttribute: s.clearAttribute,
      setAttributeNote: s.setAttributeNote,
      saveDraft: s.saveDraft,
      finalize: s.finalize,
      discardDraft: s.discardDraft,
      getEdit: s.getEdit,
      getDirty: s.getDirty,
    };
  }, []);

  const isForThisRun = active && storeRunId === runId;

  const value = useMemo<InlineReviewContextValue>(() => {
    const isEditing = isForThisRun && (status === 'reviewing' || status === 'saving');
    const dirty = actions.getDirty();

    const selectedReview = isForThisRun && reviewId
      ? {
          id: reviewId,
          runId,
          reviewerUserId: '',
          reviewerName: null,
          status: 'draft' as const,
          overallDecision: null,
          notes,
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
      loading: status === 'entering',
      saving: status === 'saving' || status === 'finalizing',
      context: isForThisRun ? context : null,
      selectedReview,
      edits: isForThisRun ? edits : {},
      dirtyCount: dirty.dirtyCount,
      dirtySummary: dirty.dirtySummary,

      startDraft: () => actions.enterReview(runId, appId),
      getEdit: (itemKey, attributeKey) => actions.getEdit(itemKey, attributeKey),
      updateAttribute: (item, attribute, patch) =>
        actions.updateAttribute(item.itemKey, attribute.key, {
          ...patch,
          itemKey: item.itemKey,
          itemType: item.itemType,
          attributeKey: attribute.key,
          originalValue: attribute.originalValue,
        }),
      acceptAttribute: (item, attribute) => actions.acceptAttribute(item, attribute),
      clearAttribute: (item, attribute) => actions.clearAttribute(item, attribute),
      correctAttribute: (item, attribute, reviewedValue) =>
        actions.correctAttribute(item, attribute, reviewedValue),
      setAttributeNote: (item, attribute, note) =>
        actions.setAttributeNote(item, attribute, note),
      saveDraft: () => actions.saveDraft(),
      finalize: () => actions.finalize(),
      discardDraft: () => actions.discardDraft(),
    };
  }, [appId, runId, isForThisRun, status, reviewId, notes, context, edits, actions]);

  if (!reviewEnabled) {
    return <>{children}</>;
  }

  return (
    <InlineReviewContext.Provider value={value}>
      {children}
    </InlineReviewContext.Provider>
  );
}
