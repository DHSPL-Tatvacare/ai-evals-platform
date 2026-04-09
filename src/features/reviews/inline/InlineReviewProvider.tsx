import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type {
  AppId,
  EvalReviewDetail,
  ReviewableAttribute,
  ReviewableItem,
  ReviewItemUpsert,
  ReviewDraftUpdate,
  RunReviewContext,
} from '@/types';
import { useAppConfig } from '@/hooks/useCurrentAppData';
import {
  fetchRunReviewContext,
  createRunReviewDraft,
  fetchReviewDetail,
  saveReviewDraft,
  finalizeReview,
  discardReviewDraft,
} from '@/services/api/reviewsApi';
import { notificationService } from '@/services/notifications';
import type { InlineEditState, InlineReviewContextValue } from './types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function reviewKey(itemKey: string, attributeKey: string): string {
  return `${itemKey}::${attributeKey}`;
}

function reviewKeyCandidates(itemKey: string, attributeKey: string): string[] {
  const exact = reviewKey(itemKey, attributeKey);
  const rawItemKey = itemKey.includes(':') ? itemKey.split(':').slice(1).join(':') : itemKey;
  const candidates = new Set<string>([
    exact,
    reviewKey(rawItemKey, attributeKey),
    reviewKey(`thread:${rawItemKey}`, attributeKey),
    reviewKey(`call:${rawItemKey}`, attributeKey),
    reviewKey(`segment:${rawItemKey}`, attributeKey),
    reviewKey(`field:${rawItemKey}`, attributeKey),
  ]);
  return Array.from(candidates);
}

function findStoredKey(
  map: Record<string, InlineEditState>,
  itemKey: string,
  attributeKey: string,
): string | null {
  for (const candidate of reviewKeyCandidates(itemKey, attributeKey)) {
    if (map[candidate]) {
      return candidate;
    }
  }
  return null;
}

function normalizeValue(value: string | null | undefined): string | null {
  if (value == null) return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function normalizeEdit(edit: InlineEditState): InlineEditState {
  return {
    ...edit,
    originalValue: normalizeValue(edit.originalValue),
    reviewedValue: edit.decision === 'correct' ? normalizeValue(edit.reviewedValue) : null,
    reasonCode: normalizeValue(edit.reasonCode),
    note: normalizeValue(edit.note),
  };
}

function areEditsEqual(a: InlineEditState | undefined, b: InlineEditState | undefined): boolean {
  if (!a && !b) return true;
  if (!a || !b) return false;

  const left = normalizeEdit(a);
  const right = normalizeEdit(b);
  return (
    left.itemKey === right.itemKey &&
    left.itemType === right.itemType &&
    left.attributeKey === right.attributeKey &&
    left.decision === right.decision &&
    left.originalValue === right.originalValue &&
    left.reviewedValue === right.reviewedValue &&
    left.reasonCode === right.reasonCode &&
    left.note === right.note
  );
}

function cleanupEdit(
  current: InlineEditState,
  baseline: InlineEditState | undefined,
): InlineEditState | null {
  const normalized = normalizeEdit(current);
  const isEmpty =
    normalized.decision === '' &&
    normalized.reviewedValue == null &&
    normalized.reasonCode == null &&
    normalized.note == null;

  if (isEmpty && !baseline) {
    return null;
  }

  return normalized;
}

function buildEditsFromReview(review: EvalReviewDetail): Record<string, InlineEditState> {
  const map: Record<string, InlineEditState> = {};
  for (const item of review.items) {
    const key = reviewKey(item.itemKey, item.attributeKey);
    map[key] = normalizeEdit({
      itemKey: item.itemKey,
      itemType: item.itemType,
      attributeKey: item.attributeKey,
      decision: item.decision,
      originalValue: item.originalValue,
      reviewedValue: item.reviewedValue,
      reasonCode: item.reasonCode,
      note: item.note,
    });
  }
  return map;
}

function toPayload(notes: string, edits: Record<string, InlineEditState>): ReviewDraftUpdate {
  const items: ReviewItemUpsert[] = Object.values(edits)
    .filter(
      (e): e is InlineEditState & { decision: 'accept' | 'reject' | 'correct' } =>
        e.decision !== '',
    )
    .map((e) => ({
      itemKey: e.itemKey,
      itemType: e.itemType,
      attributeKey: e.attributeKey,
      decision: e.decision,
      originalValue: e.originalValue,
      reviewedValue: e.decision === 'correct' ? e.reviewedValue : null,
      reasonCode: e.reasonCode,
      note: e.note,
    }));
  return { notes, items };
}

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
// Provider
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
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [context, setContext] = useState<RunReviewContext | null>(null);
  const [selectedReview, setSelectedReview] = useState<EvalReviewDetail | null>(null);
  const [edits, setEdits] = useState<Record<string, InlineEditState>>({});
  const [baselineEdits, setBaselineEdits] = useState<Record<string, InlineEditState>>({});

  // Guard against stale async completions after unmount or runId change
  const activeRunId = useRef(runId);
  activeRunId.current = runId;

  // ------ Load context on mount / when enabled ------

  const loadContext = useCallback(async () => {
    setLoading(true);
    try {
      const ctx = await fetchRunReviewContext(runId);
      if (activeRunId.current !== runId) return;
      setContext(ctx);

      const existingId = ctx.draftReviewId ?? ctx.latestReviewId;
      if (existingId) {
        const detail = await fetchReviewDetail(existingId);
        if (activeRunId.current !== runId) return;
        setSelectedReview(detail);
        const nextEdits = buildEditsFromReview(detail);
        setEdits(nextEdits);
        setBaselineEdits(nextEdits);
      } else {
        setSelectedReview(null);
        setEdits({});
        setBaselineEdits({});
      }
    } catch (err) {
      notificationService.error('Failed to load review context');
      console.error(err);
    } finally {
      if (activeRunId.current === runId) {
        setLoading(false);
      }
    }
  }, [runId]);

  useEffect(() => {
    if (reviewEnabled) {
      loadContext();
    } else {
      setContext(null);
      setSelectedReview(null);
      setEdits({});
      setBaselineEdits({});
    }
  }, [reviewEnabled, loadContext]);

  // ------ Derived state ------

  const isEditing = selectedReview?.status === 'draft';

  const { dirtyCount, dirtySummary } = useMemo(() => {
    const dirty: InlineEditState[] = [];
    const keys = new Set([...Object.keys(baselineEdits), ...Object.keys(edits)]);
    for (const key of keys) {
      if (!areEditsEqual(edits[key], baselineEdits[key]) && edits[key]) {
        dirty.push(edits[key]);
      }
    }
    const count = dirty.length;
    const summary = dirty
      .slice(0, 3)
      .map((edit) => {
        if (edit.note && edit.decision === 'accept' && edit.reviewedValue == null) {
          return `${edit.attributeKey} note`;
        }
        if (edit.decision === 'correct' && edit.reviewedValue) {
          return `${edit.attributeKey} → ${edit.reviewedValue}`;
        }
        if (edit.decision === 'accept') {
          return `${edit.attributeKey} accepted`;
        }
        return `${edit.attributeKey} updated`;
      })
      .join(', ');
    return { dirtyCount: count, dirtySummary: summary };
  }, [baselineEdits, edits]);

  // ------ Actions ------

  const getEdit = useCallback(
    (itemKey: string, attributeKey: string): InlineEditState | undefined => {
      const storedKey = findStoredKey(edits, itemKey, attributeKey);
      return storedKey ? edits[storedKey] : undefined;
    },
    [edits],
  );

  const updateAttribute = useCallback(
    (item: ReviewableItem, attribute: ReviewableAttribute, patch: Partial<InlineEditState>) => {
      const defaults: InlineEditState = {
        itemKey: item.itemKey,
        itemType: item.itemType,
        attributeKey: attribute.key,
        decision: '',
        originalValue: attribute.originalValue,
        reviewedValue: null,
        reasonCode: null,
        note: null,
      };
      setEdits((prev) => {
        const key = findStoredKey(prev, item.itemKey, attribute.key)
          ?? findStoredKey(baselineEdits, item.itemKey, attribute.key)
          ?? reviewKey(item.itemKey, attribute.key);
        const baseline = baselineEdits[key];
        const next = cleanupEdit(
          { ...defaults, ...prev[key], ...patch },
          baseline,
        );
        if (!next) {
          const { [key]: _removed, ...rest } = prev;
          return rest;
        }
        return {
          ...prev,
          [key]: next,
        };
      });
    },
    [baselineEdits],
  );

  const acceptAttribute = useCallback(
    (item: ReviewableItem, attribute: ReviewableAttribute) => {
      updateAttribute(item, attribute, { decision: 'accept' });
    },
    [updateAttribute],
  );

  const correctAttribute = useCallback(
    (item: ReviewableItem, attribute: ReviewableAttribute, reviewedValue: string) => {
      updateAttribute(item, attribute, {
        decision: 'correct',
        reviewedValue,
      });
    },
    [updateAttribute],
  );

  const setAttributeNote = useCallback(
    (item: ReviewableItem, attribute: ReviewableAttribute, note: string | null) => {
      const defaults: InlineEditState = {
        itemKey: item.itemKey,
        itemType: item.itemType,
        attributeKey: attribute.key,
        decision: '',
        originalValue: attribute.originalValue,
        reviewedValue: null,
        reasonCode: null,
        note: null,
      };

      setEdits((prev) => {
        const key = findStoredKey(prev, item.itemKey, attribute.key)
          ?? findStoredKey(baselineEdits, item.itemKey, attribute.key)
          ?? reviewKey(item.itemKey, attribute.key);
        const baseline = baselineEdits[key];
        const existing = { ...defaults, ...prev[key] };
        const normalizedNote = normalizeValue(note);
        const shouldAutoAccept =
          normalizedNote != null &&
          existing.decision === '' &&
          baseline?.decision !== 'accept';
        const onlyAutoAcceptedForNote =
          existing.decision === 'accept' &&
          existing.reviewedValue == null &&
          existing.reasonCode == null &&
          existing.note != null &&
          !baseline?.decision;

        const next = cleanupEdit(
          {
            ...existing,
            decision: shouldAutoAccept
              ? 'accept'
              : normalizedNote == null && onlyAutoAcceptedForNote
                ? ''
                : existing.decision,
            note: normalizedNote,
          },
          baseline,
        );

        if (!next) {
          const { [key]: _removed, ...rest } = prev;
          return rest;
        }

        return {
          ...prev,
          [key]: next,
        };
      });
    },
    [baselineEdits],
  );

  const startDraft = useCallback(async () => {
    setSaving(true);
    try {
      const detail = await createRunReviewDraft(runId);
      setSelectedReview(detail);
      const nextEdits = buildEditsFromReview(detail);
      setEdits(nextEdits);
      setBaselineEdits(nextEdits);
      notificationService.success('Review draft created');
    } catch (err) {
      notificationService.error('Failed to create review draft');
      console.error(err);
    } finally {
      setSaving(false);
    }
  }, [runId]);

  const handleSaveDraft = useCallback(async () => {
    if (!selectedReview) return;
    setSaving(true);
    try {
      const payload = toPayload(selectedReview.notes ?? '', edits);
      const updated = await saveReviewDraft(selectedReview.id, payload);
      setSelectedReview(updated);
      const nextEdits = buildEditsFromReview(updated);
      setEdits(nextEdits);
      setBaselineEdits(nextEdits);
      notificationService.success('Draft saved');
    } catch (err) {
      notificationService.error('Failed to save draft');
      console.error(err);
    } finally {
      setSaving(false);
    }
  }, [selectedReview, edits]);

  const handleFinalize = useCallback(async () => {
    if (!selectedReview) return;
    setSaving(true);
    try {
      const payload = toPayload(selectedReview.notes ?? '', edits);
      const updated = await finalizeReview(selectedReview.id, payload);
      setSelectedReview(updated);
      const nextEdits = buildEditsFromReview(updated);
      setEdits(nextEdits);
      setBaselineEdits(nextEdits);
      notificationService.success('Review finalized');
    } catch (err) {
      notificationService.error('Failed to finalize review');
      console.error(err);
    } finally {
      setSaving(false);
    }
  }, [selectedReview, edits]);

  const handleDiscard = useCallback(async () => {
    if (!selectedReview) return;
    setSaving(true);
    try {
      await discardReviewDraft(selectedReview.id);
      setSelectedReview(null);
      setEdits({});
      setBaselineEdits({});
      notificationService.success('Draft discarded');
      // Reload context to pick up updated history
      await loadContext();
    } catch (err) {
      notificationService.error('Failed to discard draft');
      console.error(err);
    } finally {
      setSaving(false);
    }
  }, [selectedReview, loadContext]);

  // ------ Context value ------

  const value = useMemo<InlineReviewContextValue>(
    () => ({
      appId,
      isEditing,
      hasDirtyChanges: dirtyCount > 0,
      loading,
      saving,
      context,
      selectedReview,
      edits,
      dirtyCount,
      dirtySummary,
      startDraft,
      getEdit,
      updateAttribute,
      acceptAttribute,
      correctAttribute,
      setAttributeNote,
      saveDraft: handleSaveDraft,
      finalize: handleFinalize,
      discardDraft: handleDiscard,
    }),
    [
      appId,
      isEditing,
      dirtyCount,
      loading,
      saving,
      context,
      selectedReview,
      edits,
      dirtySummary,
      startDraft,
      getEdit,
      updateAttribute,
      acceptAttribute,
      correctAttribute,
      setAttributeNote,
      handleSaveDraft,
      handleFinalize,
      handleDiscard,
    ],
  );

  if (!reviewEnabled) {
    return <>{children}</>;
  }

  return (
    <InlineReviewContext.Provider value={value}>
      {children}
    </InlineReviewContext.Provider>
  );
}
