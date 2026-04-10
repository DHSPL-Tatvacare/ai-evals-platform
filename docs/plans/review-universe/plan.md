# Review Universe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform human review into an immersive, isolated UI state with persistent dirty bar, Zustand-managed edits, framer-motion transitions, and rule-level review controls.

**Architecture:** Zustand store (`reviewModeStore`) replaces React Context as the source of truth. A `<ReviewUniverse>` layout wrapper in MainLayout renders the viewport-level chrome (border glow, persistent dirty bar, navigation blocker). Pages read from the store to hide/show elements. Existing `InlineReviewProvider` becomes a thin compatibility shim.

**Tech Stack:** Zustand (existing), framer-motion (new dependency), react-router-dom v7 useBlocker (existing), existing reviews API

**Design Spec:** `docs/plans/review-universe/design.md`

---

## File Map

### New Files
| File | Responsibility |
|------|---------------|
| `src/stores/reviewModeStore.ts` | Global Zustand store for review state, edits, actions |
| `src/features/reviews/ReviewUniverse.tsx` | Layout wrapper: mounts glow + dirty bar + nav blocker |
| `src/features/reviews/ReviewBorderGlow.tsx` | Fixed overlay with subtle animated border glow |
| `src/features/reviews/ReviewPersistentBar.tsx` | Viewport-fixed dirty bar with framer-motion enter/exit |
| `src/features/reviews/ReviewNavigationBlocker.tsx` | useBlocker + dirty modal for blocked navigation |
| `src/features/reviews/RuleReviewColumn.tsx` | Rule status dropdown + undo/notes actions column |

### Modified Files
| File | Change |
|------|--------|
| `src/components/layout/MainLayout.tsx` | Mount `<ReviewUniverse />` |
| `src/features/reviews/inline/InlineReviewProvider.tsx` | Refactor to read from Zustand store |
| `src/features/reviews/inline/index.ts` | Re-export new store |
| `src/features/evalRuns/pages/RunDetail.tsx` | Conditional hide/show elements, framer-motion wrapping |
| `src/features/evalRuns/pages/ThreadDetailV2.tsx` | Hide start review button, wire rules tab review |
| `src/features/evalRuns/components/threadReview/RuleComplianceTab.tsx` | Add review columns to rule table |
| `src/features/chat-widget/ChatWidget.tsx` | Hide FAB when review active |
| `src/features/evalRuns/components/RunHeaderActions.tsx` | Hide buttons when review active |
| `src/features/reviews/inline/VerdictDropdown.tsx` | Show BeforeAfterChip for saved edits |

---

## Task 1: Install framer-motion

**Files:**
- Modify: `package.json`

- [ ] **Step 1: Install dependency**

```bash
npm install framer-motion
```

- [ ] **Step 2: Verify installation**

```bash
node -e "require('framer-motion'); console.log('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add package.json package-lock.json
git commit -m "chore: add framer-motion for review universe transitions"
```

---

## Task 2: Create reviewModeStore

**Files:**
- Create: `src/stores/reviewModeStore.ts`

- [ ] **Step 1: Create the store**

```typescript
import { create } from 'zustand';
import type { AppId } from '@/types';
import type {
  RunReviewContext,
  EvalReviewDetail,
  ReviewableItem,
  ReviewableAttribute,
  ReviewItemUpsert,
} from '@/types/reviews';
import type { InlineEditState } from '@/features/reviews/inline/types';
import {
  fetchRunReviewContext,
  createRunReviewDraft,
  fetchReviewDetail,
  saveReviewDraft,
  finalizeReview,
  discardReviewDraft,
} from '@/services/api/reviewsApi';
import { notificationService } from '@/services/notifications';

// ---------------------------------------------------------------------------
// Helpers (lifted from InlineReviewProvider — shared logic)
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
    if (map[candidate]) return candidate;
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
  if (isEmpty && !baseline) return null;
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

function toPayload(notes: string, edits: Record<string, InlineEditState>) {
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

function computeDirty(
  edits: Record<string, InlineEditState>,
  baselineEdits: Record<string, InlineEditState>,
): { dirtyCount: number; dirtySummary: string } {
  const allKeys = new Set([...Object.keys(edits), ...Object.keys(baselineEdits)]);
  const dirtyKeys: string[] = [];
  for (const key of allKeys) {
    if (!areEditsEqual(edits[key], baselineEdits[key])) {
      dirtyKeys.push(key);
    }
  }
  const summaryParts = dirtyKeys.slice(0, 3).map((key) => {
    const edit = edits[key];
    if (!edit) return key;
    const label = edit.attributeKey || key;
    if (edit.decision === 'accept') return `${label} accepted`;
    if (edit.decision === 'correct') return `${label} → ${edit.reviewedValue}`;
    if (edit.decision === 'reject') return `${label} rejected`;
    return label;
  });
  return {
    dirtyCount: dirtyKeys.length,
    dirtySummary: summaryParts.join(', ') + (dirtyKeys.length > 3 ? ` +${dirtyKeys.length - 3} more` : ''),
  };
}

// ---------------------------------------------------------------------------
// Store types
// ---------------------------------------------------------------------------

export type ReviewModeStatus = 'idle' | 'entering' | 'reviewing' | 'saving' | 'finalizing' | 'exiting';

interface ReviewModeState {
  active: boolean;
  runId: string | null;
  appId: AppId | null;
  reviewId: string | null;
  status: ReviewModeStatus;
  context: RunReviewContext | null;
  edits: Record<string, InlineEditState>;
  baselineEdits: Record<string, InlineEditState>;
  notes: string;

  enterReview: (runId: string, appId: AppId) => Promise<void>;
  updateAttribute: (itemKey: string, attrKey: string, patch: Partial<InlineEditState>) => void;
  acceptAttribute: (item: ReviewableItem, attr: ReviewableAttribute) => void;
  correctAttribute: (item: ReviewableItem, attr: ReviewableAttribute, reviewedValue: string) => void;
  clearAttribute: (item: ReviewableItem, attr: ReviewableAttribute) => void;
  setAttributeNote: (item: ReviewableItem, attr: ReviewableAttribute, note: string | null) => void;
  saveDraft: () => Promise<void>;
  finalize: () => Promise<void>;
  discardDraft: () => Promise<void>;
  exitReview: () => void;

  getEdit: (itemKey: string, attrKey: string) => InlineEditState | undefined;
  isAttributeSaved: (itemKey: string, attrKey: string) => boolean;
  getDirty: () => { dirtyCount: number; dirtySummary: string; isDirty: boolean };
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

const INITIAL_STATE = {
  active: false,
  runId: null as string | null,
  appId: null as AppId | null,
  reviewId: null as string | null,
  status: 'idle' as ReviewModeStatus,
  context: null as RunReviewContext | null,
  edits: {} as Record<string, InlineEditState>,
  baselineEdits: {} as Record<string, InlineEditState>,
  notes: '',
};

export const useReviewModeStore = create<ReviewModeState>()((set, get) => ({
  ...INITIAL_STATE,

  enterReview: async (runId, appId) => {
    set({ status: 'entering', runId, appId });

    // Close Sherlock if open
    try {
      const { useChatWidgetStore } = await import('@/features/chat-widget/useChatWidget');
      const chatState = useChatWidgetStore.getState();
      if (chatState.open) chatState.toggle();
    } catch { /* chat widget may not exist */ }

    try {
      const ctx = await fetchRunReviewContext(runId);
      const draft = await createRunReviewDraft(runId);
      const edits = buildEditsFromReview(draft);
      const baselineEdits = { ...edits };
      set({
        active: true,
        status: 'reviewing',
        reviewId: draft.id,
        context: ctx,
        edits,
        baselineEdits,
        notes: draft.notes ?? '',
      });
    } catch (err) {
      notificationService.error(err instanceof Error ? err.message : 'Failed to start review');
      set(INITIAL_STATE);
    }
  },

  updateAttribute: (itemKey, attrKey, patch) => {
    const { edits, baselineEdits } = get();
    const storedKey = findStoredKey(edits, itemKey, attrKey) ?? reviewKey(itemKey, attrKey);
    const current = edits[storedKey] ?? {
      itemKey, itemType: '', attributeKey: attrKey,
      decision: '' as const, originalValue: null, reviewedValue: null,
      reasonCode: null, note: null,
    };
    const updated = { ...current, ...patch };
    const cleaned = cleanupEdit(updated, baselineEdits[storedKey]);
    if (cleaned) {
      set({ edits: { ...edits, [storedKey]: cleaned } });
    } else {
      const next = { ...edits };
      delete next[storedKey];
      set({ edits: next });
    }
  },

  acceptAttribute: (item, attr) => {
    const key = reviewKey(item.itemKey, attr.key);
    get().updateAttribute(item.itemKey, attr.key, {
      itemKey: item.itemKey,
      itemType: item.itemType,
      attributeKey: attr.key,
      decision: 'accept',
      originalValue: attr.originalValue,
    });
  },

  correctAttribute: (item, attr, reviewedValue) => {
    get().updateAttribute(item.itemKey, attr.key, {
      itemKey: item.itemKey,
      itemType: item.itemType,
      attributeKey: attr.key,
      decision: 'correct',
      originalValue: attr.originalValue,
      reviewedValue,
    });
  },

  clearAttribute: (item, attr) => {
    const { edits, baselineEdits } = get();
    const storedKey = findStoredKey(edits, item.itemKey, attr.key) ?? reviewKey(item.itemKey, attr.key);
    const baseline = baselineEdits[storedKey];
    if (baseline) {
      // Reset to baseline
      set({ edits: { ...edits, [storedKey]: { ...baseline } } });
    } else {
      const next = { ...edits };
      delete next[storedKey];
      set({ edits: next });
    }
  },

  setAttributeNote: (item, attr, note) => {
    const { edits } = get();
    const storedKey = findStoredKey(edits, item.itemKey, attr.key) ?? reviewKey(item.itemKey, attr.key);
    const current = edits[storedKey];
    const decision = current?.decision || 'accept';
    get().updateAttribute(item.itemKey, attr.key, {
      itemKey: item.itemKey,
      itemType: item.itemType,
      attributeKey: attr.key,
      decision,
      originalValue: attr.originalValue,
      note,
    });
  },

  saveDraft: async () => {
    const { reviewId, notes, edits } = get();
    if (!reviewId) return;
    set({ status: 'saving' });
    try {
      const payload = toPayload(notes, edits);
      const updated = await saveReviewDraft(reviewId, payload);
      const newEdits = buildEditsFromReview(updated);
      set({
        status: 'reviewing',
        edits: newEdits,
        baselineEdits: { ...newEdits },
        notes: updated.notes ?? '',
      });
      notificationService.success('Draft saved');
    } catch (err) {
      set({ status: 'reviewing' });
      notificationService.error(err instanceof Error ? err.message : 'Failed to save draft');
    }
  },

  finalize: async () => {
    const { reviewId, notes, edits } = get();
    if (!reviewId) return;
    set({ status: 'finalizing' });
    try {
      const payload = toPayload(notes, edits);
      await finalizeReview(reviewId, payload);
      notificationService.success('Review finalized');
      set({ status: 'exiting' });
      // Delay reset to allow exit animation
      setTimeout(() => get().exitReview(), 500);
    } catch (err) {
      set({ status: 'reviewing' });
      notificationService.error(err instanceof Error ? err.message : 'Failed to finalize review');
    }
  },

  discardDraft: async () => {
    const { reviewId } = get();
    if (!reviewId) return;
    try {
      await discardReviewDraft(reviewId);
      notificationService.success('Draft discarded');
      set({ status: 'exiting' });
      setTimeout(() => get().exitReview(), 500);
    } catch (err) {
      notificationService.error(err instanceof Error ? err.message : 'Failed to discard draft');
    }
  },

  exitReview: () => {
    set(INITIAL_STATE);
  },

  getEdit: (itemKey, attrKey) => {
    const { edits } = get();
    const storedKey = findStoredKey(edits, itemKey, attrKey);
    return storedKey ? edits[storedKey] : undefined;
  },

  isAttributeSaved: (itemKey, attrKey) => {
    const { baselineEdits } = get();
    const storedKey = findStoredKey(baselineEdits, itemKey, attrKey);
    if (!storedKey) return false;
    const baseline = baselineEdits[storedKey];
    return !!baseline && baseline.decision !== '';
  },

  getDirty: () => {
    const { edits, baselineEdits } = get();
    const result = computeDirty(edits, baselineEdits);
    return { ...result, isDirty: result.dirtyCount > 0 };
  },
}));
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
npx tsc --noEmit 2>&1 | grep reviewModeStore | head -10
```

Expected: No errors (or only unused import warnings from files not yet modified).

- [ ] **Step 3: Commit**

```bash
git add src/stores/reviewModeStore.ts
git commit -m "feat: add reviewModeStore — global Zustand store for review universe"
```

---

## Task 3: Create ReviewBorderGlow component

**Files:**
- Create: `src/features/reviews/ReviewBorderGlow.tsx`

- [ ] **Step 1: Create the component**

```typescript
import { motion, AnimatePresence } from 'framer-motion';
import { useReviewModeStore } from '@/stores/reviewModeStore';

export function ReviewBorderGlow() {
  const active = useReviewModeStore((s) => s.active);

  return (
    <AnimatePresence>
      {active && (
        <motion.div
          key="review-glow"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.4, ease: 'easeInOut' }}
          className="review-border-glow"
          style={{
            position: 'fixed',
            inset: 0,
            pointerEvents: 'none',
            zIndex: 'var(--z-overlay)' as unknown as number,
            boxShadow: 'inset 0 0 30px 0 color-mix(in srgb, var(--color-brand-primary) 12%, transparent)',
          }}
        />
      )}
    </AnimatePresence>
  );
}
```

- [ ] **Step 2: Add the CSS animation to `src/styles/globals.css`**

Append at the end of the file, before the closing of the last block:

```css
/* Review Universe — subtle border glow breathe */
.review-border-glow {
  animation: review-glow-breathe 3s ease-in-out infinite;
}

@keyframes review-glow-breathe {
  0%, 100% {
    box-shadow: inset 0 0 30px 0 color-mix(in srgb, var(--color-brand-primary) 10%, transparent);
  }
  50% {
    box-shadow: inset 0 0 40px 0 color-mix(in srgb, var(--color-brand-primary) 18%, transparent);
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add src/features/reviews/ReviewBorderGlow.tsx src/styles/globals.css
git commit -m "feat: add ReviewBorderGlow — subtle animated viewport glow for review mode"
```

---

## Task 4: Create ReviewPersistentBar component

**Files:**
- Create: `src/features/reviews/ReviewPersistentBar.tsx`

- [ ] **Step 1: Create the component**

```typescript
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { PencilLine, Save, SendHorizontal, Trash2 } from 'lucide-react';
import { Button, ConfirmDialog } from '@/components/ui';
import { useReviewModeStore } from '@/stores/reviewModeStore';

export function ReviewPersistentBar() {
  const active = useReviewModeStore((s) => s.active);
  const status = useReviewModeStore((s) => s.status);
  const saveDraft = useReviewModeStore((s) => s.saveDraft);
  const finalize = useReviewModeStore((s) => s.finalize);
  const discardDraft = useReviewModeStore((s) => s.discardDraft);
  const getDirty = useReviewModeStore((s) => s.getDirty);
  const [discardOpen, setDiscardOpen] = useState(false);

  const { dirtyCount, dirtySummary, isDirty } = getDirty();
  const saving = status === 'saving' || status === 'finalizing';
  const showBar = active && status !== 'exiting';

  return (
    <>
      <AnimatePresence>
        {showBar && (
          <motion.div
            key="review-bar"
            initial={{ y: 60, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 60, opacity: 0 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className="fixed bottom-0 left-0 right-0 z-[var(--z-sticky)] border-t border-[var(--interactive-primary)]/25 bg-[color-mix(in_srgb,var(--interactive-primary)_9%,var(--bg-primary))] px-6 py-3 shadow-[0_-10px_24px_color-mix(in_srgb,var(--interactive-primary)_10%,transparent)] backdrop-blur-sm"
          >
            <div className="flex items-center justify-between">
              <div className="min-w-0">
                {isDirty ? (
                  <div className="flex items-center gap-2 text-[12px] font-semibold text-[var(--text-brand)]">
                    <span className="h-1.5 w-1.5 rounded-full bg-[var(--text-brand)] animate-pulse" />
                    {dirtyCount} unsaved {dirtyCount === 1 ? 'change' : 'changes'}
                    {dirtySummary && (
                      <span className="font-normal text-[var(--text-secondary)] truncate max-w-[400px]">
                        — {dirtySummary}
                      </span>
                    )}
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-[12px] font-medium text-[var(--text-secondary)]">
                    <PencilLine className="h-3.5 w-3.5" />
                    Review in progress
                  </div>
                )}
              </div>
              <div className="flex gap-1.5">
                <Button variant="ghost" size="sm" icon={Trash2} onClick={() => setDiscardOpen(true)} disabled={saving}>
                  Discard
                </Button>
                {isDirty && (
                  <Button variant="secondary" size="sm" icon={Save} onClick={() => void saveDraft()} isLoading={status === 'saving'}>
                    Save Draft
                  </Button>
                )}
                <Button size="sm" icon={SendHorizontal} onClick={() => void finalize()} isLoading={status === 'finalizing'}>
                  Finalize
                </Button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <ConfirmDialog
        isOpen={discardOpen}
        onClose={() => setDiscardOpen(false)}
        onConfirm={() => {
          setDiscardOpen(false);
          void discardDraft();
        }}
        title="Discard review draft"
        description={isDirty
          ? 'Discard the current review draft and all unsaved changes? This cannot be undone.'
          : 'Discard the review draft? This cannot be undone.'}
        confirmLabel="Discard"
        variant="danger"
      />
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add src/features/reviews/ReviewPersistentBar.tsx
git commit -m "feat: add ReviewPersistentBar — persistent viewport-bottom dirty bar"
```

---

## Task 5: Create ReviewNavigationBlocker component

**Files:**
- Create: `src/features/reviews/ReviewNavigationBlocker.tsx`

- [ ] **Step 1: Create the component**

```typescript
import { useEffect, useCallback, useState } from 'react';
import { useBlocker } from 'react-router-dom';
import { useReviewModeStore } from '@/stores/reviewModeStore';
import { ConfirmDialog } from '@/components/ui';

export function ReviewNavigationBlocker() {
  const active = useReviewModeStore((s) => s.active);
  const runId = useReviewModeStore((s) => s.runId);
  const saveDraft = useReviewModeStore((s) => s.saveDraft);
  const discardDraft = useReviewModeStore((s) => s.discardDraft);
  const getDirty = useReviewModeStore((s) => s.getDirty);

  // Determine allowed route patterns for the active review
  const isAllowedRoute = useCallback(
    (pathname: string): boolean => {
      if (!active || !runId) return true;
      // Allow run detail for this run
      if (pathname.includes(`/runs/${runId}`)) return true;
      // Allow thread detail pages (thread IDs are navigated from run detail)
      if (pathname.includes('/threads/')) return true;
      return false;
    },
    [active, runId],
  );

  // Block navigation via react-router
  const blocker = useBlocker(
    useCallback(
      ({ nextLocation }) => {
        if (!active) return false;
        return !isAllowedRoute(nextLocation.pathname);
      },
      [active, isAllowedRoute],
    ),
  );

  // Block browser close/refresh
  useEffect(() => {
    if (!active) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [active]);

  const handleSaveAndLeave = async () => {
    await saveDraft();
    blocker.proceed?.();
  };

  const handleDiscardAndLeave = async () => {
    await discardDraft();
    // discardDraft triggers exitReview after timeout — blocker will unblock
  };

  if (blocker.state !== 'blocked') return null;

  return (
    <ConfirmDialog
      isOpen
      onClose={() => blocker.reset?.()}
      onConfirm={() => void handleDiscardAndLeave()}
      title="Unsaved review changes"
      description="You have unsaved review changes. Save your draft before leaving, or discard to lose changes."
      confirmLabel="Discard & Leave"
      variant="danger"
      extraActions={[
        {
          label: 'Save Draft & Leave',
          onClick: () => void handleSaveAndLeave(),
          variant: 'primary' as const,
        },
      ]}
    />
  );
}
```

- [ ] **Step 2: Check if ConfirmDialog supports `extraActions` prop**

Read `src/components/ui/ConfirmDialog.tsx` and check props. If `extraActions` is not supported, add it:

```typescript
// Add to ConfirmDialogProps interface:
extraActions?: { label: string; onClick: () => void; variant?: 'primary' | 'secondary' }[];

// Add in the footer, before the confirm button:
{extraActions?.map((action) => (
  <Button key={action.label} variant={action.variant ?? 'secondary'} onClick={action.onClick}>
    {action.label}
  </Button>
))}
```

- [ ] **Step 3: Commit**

```bash
git add src/features/reviews/ReviewNavigationBlocker.tsx src/components/ui/ConfirmDialog.tsx
git commit -m "feat: add ReviewNavigationBlocker — blocks navigation outside review universe"
```

---

## Task 6: Create ReviewUniverse layout wrapper

**Files:**
- Create: `src/features/reviews/ReviewUniverse.tsx`
- Modify: `src/components/layout/MainLayout.tsx`

- [ ] **Step 1: Create the wrapper component**

```typescript
import { ReviewBorderGlow } from './ReviewBorderGlow';
import { ReviewPersistentBar } from './ReviewPersistentBar';
import { ReviewNavigationBlocker } from './ReviewNavigationBlocker';

export function ReviewUniverse() {
  return (
    <>
      <ReviewBorderGlow />
      <ReviewPersistentBar />
      <ReviewNavigationBlocker />
    </>
  );
}
```

- [ ] **Step 2: Mount in MainLayout**

In `src/components/layout/MainLayout.tsx`, add import and render:

```typescript
// Add import at top:
import { ReviewUniverse } from '@/features/reviews/ReviewUniverse';

// Add inside the return JSX, after <ChatWidget /> (around line 85):
<ReviewUniverse />
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
npx tsc --noEmit 2>&1 | head -20
```

Expected: No errors related to review files.

- [ ] **Step 4: Commit**

```bash
git add src/features/reviews/ReviewUniverse.tsx src/components/layout/MainLayout.tsx
git commit -m "feat: mount ReviewUniverse layout wrapper in MainLayout"
```

---

## Task 7: Refactor InlineReviewProvider as compatibility shim

**Files:**
- Modify: `src/features/reviews/inline/InlineReviewProvider.tsx`

- [ ] **Step 1: Refactor the provider**

Replace the internal state management with a bridge to the Zustand store. The provider still creates the Context (so existing `useInlineReview()` consumers work), but delegates all state and actions to `reviewModeStore`.

Key changes:
- Remove local `edits`, `baselineEdits`, `selectedReview`, `context` state
- Read from `useReviewModeStore` instead
- `startDraft()` calls `reviewModeStore.enterReview(runId, appId)`
- `getEdit()` calls `reviewModeStore.getEdit()`
- `updateAttribute()`, `acceptAttribute()`, `correctAttribute()`, `clearAttribute()`, `setAttributeNote()` delegate to store
- `saveDraft()`, `finalize()`, `discardDraft()` delegate to store
- `isEditing` derived from `reviewModeStore.active && reviewModeStore.status === 'reviewing'`
- `dirtyCount`, `dirtySummary` from `reviewModeStore.getDirty()`

The provider still accepts `runId`, `appId`, `enabled` props but no longer manages its own loading lifecycle. It becomes a thin mapping layer.

```typescript
import { createContext, useContext, type ReactNode } from 'react';
import type { AppId } from '@/types';
import type { InlineReviewContextValue } from './types';
import { useReviewModeStore } from '@/stores/reviewModeStore';

const InlineReviewContext = createContext<InlineReviewContextValue | null>(null);

export function useInlineReview(): InlineReviewContextValue {
  const ctx = useContext(InlineReviewContext);
  if (!ctx) throw new Error('useInlineReview must be used inside InlineReviewProvider');
  return ctx;
}

export function useInlineReviewOptional(): InlineReviewContextValue | null {
  return useContext(InlineReviewContext);
}

interface InlineReviewProviderProps {
  runId: string;
  appId: AppId;
  enabled: boolean;
  children: ReactNode;
}

export function InlineReviewProvider({ runId, appId, enabled, children }: InlineReviewProviderProps) {
  const store = useReviewModeStore();

  // Only provide context if the store is active for THIS run
  const isActiveForThisRun = store.active && store.runId === runId;

  const value: InlineReviewContextValue = {
    appId,
    isEditing: isActiveForThisRun && (store.status === 'reviewing' || store.status === 'saving'),
    hasDirtyChanges: isActiveForThisRun ? store.getDirty().isDirty : false,
    loading: store.status === 'entering',
    saving: store.status === 'saving' || store.status === 'finalizing',
    context: store.context,
    selectedReview: isActiveForThisRun ? {
      id: store.reviewId ?? '',
      runId,
      status: store.status === 'finalizing' ? 'final' : 'draft',
      items: [],
      notes: store.notes,
      reviewerUserId: '',
      overallDecision: null,
      reviewSnapshot: null,
      createdAt: '',
      updatedAt: '',
      completedAt: null,
    } : null,
    edits: isActiveForThisRun ? store.edits : {},
    dirtyCount: isActiveForThisRun ? store.getDirty().dirtyCount : 0,
    dirtySummary: isActiveForThisRun ? store.getDirty().dirtySummary : '',
    startDraft: () => store.enterReview(runId, appId),
    getEdit: (itemKey, attrKey) => isActiveForThisRun ? store.getEdit(itemKey, attrKey) : undefined,
    updateAttribute: (item, attr, patch) => store.updateAttribute(item.itemKey, attr.key, patch),
    acceptAttribute: (item, attr) => store.acceptAttribute(item, attr),
    clearAttribute: (item, attr) => store.clearAttribute(item, attr),
    correctAttribute: (item, attr, val) => store.correctAttribute(item, attr, val),
    setAttributeNote: (item, attr, note) => store.setAttributeNote(item, attr, note),
    saveDraft: () => store.saveDraft(),
    finalize: () => store.finalize(),
    discardDraft: () => store.discardDraft(),
  };

  if (!enabled) {
    return <InlineReviewContext.Provider value={null}>{children}</InlineReviewContext.Provider>;
  }

  return <InlineReviewContext.Provider value={value}>{children}</InlineReviewContext.Provider>;
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 3: Commit**

```bash
git add src/features/reviews/inline/InlineReviewProvider.tsx
git commit -m "refactor: InlineReviewProvider delegates to reviewModeStore"
```

---

## Task 8: Update RunDetail page for review mode transitions

**Files:**
- Modify: `src/features/evalRuns/pages/RunDetail.tsx`

- [ ] **Step 1: Add framer-motion imports and review store**

```typescript
// Add imports:
import { motion, AnimatePresence } from 'framer-motion';
import { useReviewModeStore } from '@/stores/reviewModeStore';
```

- [ ] **Step 2: Read review mode state in the component**

Inside the component, after existing hooks:

```typescript
const reviewActive = useReviewModeStore((s) => s.active);
const reviewRunId = useReviewModeStore((s) => s.runId);
const isInReview = reviewActive && reviewRunId === run?.run_id;
```

- [ ] **Step 3: Wrap hideable header elements in AnimatePresence**

In the `RunHeaderActions` usage, conditionally hide buttons:

```typescript
<RunHeaderActions
  logsHref={`${routes.kaira.logs}?run_id=${run.run_id}`}
  isActive={isRunActive}
  cancelling={cancelling}
  deleting={deleting}
  onCancel={handleCancel}
  onDelete={() => setConfirmDelete(true)}
  visibilityContent={isInReview ? null : (
    <EvalRunVisibilityPanel ... />
  )}
  reviewContent={isInReview ? null : <StartReviewButton />}
  hideActions={isInReview}
/>
```

Update `RunHeaderActions` to accept `hideActions` prop — when true, hide Logs, Delete, Cancel buttons:

```typescript
// In RunHeaderActions interface, add:
hideActions?: boolean;

// In the JSX, wrap the action buttons:
{!hideActions && (
  <>
    <span className="mx-0.5 h-4 w-px bg-[var(--border-subtle)]" />
    <ActionIconLink ... />
    {isActive && <PermissionGate ...> ... </PermissionGate>}
    <PermissionGate ...> ... </PermissionGate>
  </>
)}
```

- [ ] **Step 4: Make breadcrumb "Runs" inert during review**

Find the breadcrumb that links to runs list. When `isInReview`, render as `<span>` instead of `<Link>`:

```typescript
{isInReview ? (
  <span className="text-[var(--text-muted)]">Runs</span>
) : (
  <Link to={routes.kaira.runs} className="hover:text-[var(--text-brand)]">Runs</Link>
)}
```

- [ ] **Step 5: Filter tabs during review**

Where the tabs array is built, remove the 'report' tab when in review:

```typescript
// Where ReviewAwareRunTabs is rendered, or where tabs are defined:
// Filter out report tab when in review
const visibleTabs = isInReview
  ? tabs.filter((t) => t.id !== 'report')
  : tabs;
```

- [ ] **Step 6: Remove old DirtyBar/ReviewDirtyBar/ReviewLinkGuard from RunDetail**

The persistent bar in `ReviewUniverse` replaces all of these. Remove or no-op:
- `ReviewDirtyBar` component usage
- `ReviewLinkGuard` component usage
- `useInlineReviewNavigationGuard` usage

These are now handled globally by `ReviewUniverse`.

- [ ] **Step 7: Verify TypeScript compiles**

```bash
npx tsc --noEmit 2>&1 | grep -i "RunDetail\|RunHeader" | head -10
```

- [ ] **Step 8: Commit**

```bash
git add src/features/evalRuns/pages/RunDetail.tsx src/features/evalRuns/components/RunHeaderActions.tsx
git commit -m "feat: RunDetail hides elements and removes report tab during review mode"
```

---

## Task 9: Update ThreadDetailV2 for review mode

**Files:**
- Modify: `src/features/evalRuns/pages/ThreadDetailV2.tsx`

- [ ] **Step 1: Hide StartReview button when already in review**

```typescript
import { useReviewModeStore } from '@/stores/reviewModeStore';

// In the component:
const reviewActive = useReviewModeStore((s) => s.active);

// Where StartReview button is rendered, wrap with:
{!reviewActive && <StartReviewButton />}
```

- [ ] **Step 2: Verify left/right thread navigation works**

The existing `goToThread()` navigates to `/kaira/threads/{threadId}` which is in the allowed routes for `ReviewNavigationBlocker`. No changes needed — the navigation will be allowed and edits persist in the Zustand store keyed by `itemKey::attributeKey` (not by current thread).

Confirm by reading `goToThread` implementation — it should use `navigate(routes.kaira.threadDetail(id))`.

- [ ] **Step 3: Commit**

```bash
git add src/features/evalRuns/pages/ThreadDetailV2.tsx
git commit -m "feat: ThreadDetailV2 hides start review button when in review mode"
```

---

## Task 10: Add rule-level review controls to RuleComplianceTab

**Files:**
- Create: `src/features/reviews/RuleReviewColumn.tsx`
- Modify: `src/features/evalRuns/components/threadReview/RuleComplianceTab.tsx`

- [ ] **Step 1: Create RuleReviewColumn component**

```typescript
import { useState } from 'react';
import { Undo2, MessageCircle } from 'lucide-react';
import { Tooltip } from '@/components/ui';
import { cn } from '@/utils/cn';
import type { ReviewableItem, ReviewableAttribute } from '@/types/reviews';
import type { InlineEditState } from '@/features/reviews/inline/types';
import { useReviewModeStore } from '@/stores/reviewModeStore';
import { NoteModal } from './NoteModal';

interface RuleReviewStatusProps {
  item: ReviewableItem;
  attr: ReviewableAttribute;
  edit: InlineEditState | undefined;
  isSaved: boolean;
}

export function RuleReviewStatus({ item, attr, edit, isSaved }: RuleReviewStatusProps) {
  const correctAttribute = useReviewModeStore((s) => s.correctAttribute);
  const currentValue = edit?.decision === 'correct' ? edit.reviewedValue : attr.originalValue;

  return (
    <select
      value={currentValue ?? ''}
      onChange={(e) => correctAttribute(item, attr, e.target.value)}
      className={cn(
        'text-xs px-2 py-1 rounded border bg-[var(--bg-secondary)] text-[var(--text-primary)]',
        'border-[var(--border-default)] focus:border-[var(--color-brand-primary)] focus:outline-none',
        edit?.decision === 'correct' && 'border-[var(--color-warning)] bg-[var(--surface-warning)]',
      )}
    >
      {attr.allowedValues.map((v) => (
        <option key={v} value={v}>{v}</option>
      ))}
    </select>
  );
}

interface RuleReviewActionsProps {
  item: ReviewableItem;
  attr: ReviewableAttribute;
  edit: InlineEditState | undefined;
}

export function RuleReviewActions({ item, attr, edit }: RuleReviewActionsProps) {
  const clearAttribute = useReviewModeStore((s) => s.clearAttribute);
  const setAttributeNote = useReviewModeStore((s) => s.setAttributeNote);
  const [noteOpen, setNoteOpen] = useState(false);
  const hasOverride = edit?.decision === 'correct' || edit?.decision === 'reject';
  const hasNote = !!edit?.note;

  return (
    <div className="flex items-center gap-1">
      {hasOverride && (
        <Tooltip content="Undo override">
          <button
            onClick={() => clearAttribute(item, attr)}
            className="inline-flex h-6 w-6 items-center justify-center rounded text-[var(--text-muted)] hover:text-[var(--color-warning)] hover:bg-[var(--surface-warning)] transition-colors"
          >
            <Undo2 className="h-3 w-3" />
          </button>
        </Tooltip>
      )}
      <Tooltip content={hasNote ? 'Edit note' : 'Add note'}>
        <button
          onClick={() => setNoteOpen(true)}
          className={cn(
            'inline-flex h-6 w-6 items-center justify-center rounded transition-colors',
            hasNote
              ? 'text-[var(--color-brand-primary)] hover:bg-[var(--color-brand-accent)]'
              : 'text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]',
          )}
        >
          <MessageCircle className="h-3 w-3" />
        </button>
      </Tooltip>
      {noteOpen && (
        <NoteModal
          initialNote={edit?.note ?? ''}
          onSave={(note) => {
            setAttributeNote(item, attr, note || null);
            setNoteOpen(false);
          }}
          onClose={() => setNoteOpen(false)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create NoteModal helper if it doesn't exist**

Check if a note modal already exists in `InlineReviewControls.tsx`. If so, extract it. If not, create a simple one:

```typescript
// src/features/reviews/NoteModal.tsx
import { useState } from 'react';
import { Button } from '@/components/ui';

interface NoteModalProps {
  initialNote: string;
  onSave: (note: string) => void;
  onClose: () => void;
}

export function NoteModal({ initialNote, onSave, onClose }: NoteModalProps) {
  const [note, setNote] = useState(initialNote);

  return (
    <div className="fixed inset-0 z-[var(--z-modal)] flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="bg-[var(--bg-primary)] rounded-lg border border-[var(--border-default)] p-4 w-80 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-2">Review Note</h3>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          className="w-full h-24 text-xs p-2 rounded border border-[var(--border-default)] bg-[var(--bg-secondary)] text-[var(--text-primary)] resize-none focus:border-[var(--color-brand-primary)] focus:outline-none"
          placeholder="Add a note for this review decision..."
          autoFocus
        />
        <div className="flex justify-end gap-2 mt-3">
          <Button size="sm" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={() => onSave(note)}>Save</Button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Wire into RuleComplianceTab**

In `src/features/evalRuns/components/threadReview/RuleComplianceTab.tsx`, add the review columns to the rule table when in review mode:

```typescript
import { useReviewModeStore } from '@/stores/reviewModeStore';
import { RuleReviewStatus, RuleReviewActions } from '@/features/reviews/RuleReviewColumn';

// In the component:
const reviewActive = useReviewModeStore((s) => s.active);
const getEdit = useReviewModeStore((s) => s.getEdit);
const isAttributeSaved = useReviewModeStore((s) => s.isAttributeSaved);

// In the table header row, add columns when reviewActive:
{reviewActive && <th>Review Status</th>}
{reviewActive && <th>Actions</th>}

// In each rule row, add cells:
{reviewActive && ruleAttr && reviewableItem && (
  <td>
    <RuleReviewStatus
      item={reviewableItem}
      attr={ruleAttr}
      edit={getEdit(reviewableItem.itemKey, ruleAttr.key)}
      isSaved={isAttributeSaved(reviewableItem.itemKey, ruleAttr.key)}
    />
  </td>
)}
{reviewActive && ruleAttr && reviewableItem && (
  <td>
    <RuleReviewActions
      item={reviewableItem}
      attr={ruleAttr}
      edit={getEdit(reviewableItem.itemKey, ruleAttr.key)}
    />
  </td>
)}
```

- [ ] **Step 4: Commit**

```bash
git add src/features/reviews/RuleReviewColumn.tsx src/features/reviews/NoteModal.tsx src/features/evalRuns/components/threadReview/RuleComplianceTab.tsx
git commit -m "feat: add rule-level review controls — status dropdown + undo/notes column"
```

---

## Task 11: Hide ChatWidget FAB during review

**Files:**
- Modify: `src/features/chat-widget/ChatWidget.tsx`

- [ ] **Step 1: Add review mode check**

```typescript
import { useReviewModeStore } from '@/stores/reviewModeStore';

// Inside ChatWidget component, after existing hooks:
const reviewActive = useReviewModeStore((s) => s.active);

// Before the chatConfig.enabled check:
if (reviewActive) return null;
```

- [ ] **Step 2: Commit**

```bash
git add src/features/chat-widget/ChatWidget.tsx
git commit -m "feat: hide ChatWidget FAB during review mode"
```

---

## Task 12: Fix BeforeAfterChip visibility for saved edits

**Files:**
- Modify: `src/features/reviews/inline/VerdictDropdown.tsx`

- [ ] **Step 1: Read current VerdictDropdown implementation**

Read `src/features/reviews/inline/VerdictDropdown.tsx` to understand the current BeforeAfterChip rendering logic.

- [ ] **Step 2: Update chip visibility logic**

The chip should show when:
- Not currently editing AND value differs from original (existing behavior)
- OR currently editing AND the attribute has been saved (`isAttributeSaved` returns true) AND value differs from original

```typescript
import { useReviewModeStore } from '@/stores/reviewModeStore';

// In the component:
const isAttributeSaved = useReviewModeStore((s) => s.isAttributeSaved);

// Update the condition for showing BeforeAfterChip:
const showChip = !isEditing
  ? value !== originalValue
  : isAttributeSaved(itemKey, attributeKey) && value !== originalValue;

// When showChip is true and isEditing, render BOTH the chip AND the dropdown:
{showChip && <BeforeAfterChip before={originalValue} after={value} category={category} />}
{isEditing && <Select ... />}
```

The exact implementation depends on the current VerdictDropdown structure — adapt the condition to fit.

- [ ] **Step 3: Commit**

```bash
git add src/features/reviews/inline/VerdictDropdown.tsx
git commit -m "fix: show BeforeAfterChip for saved edits during review mode"
```

---

## Task 13: Update barrel exports

**Files:**
- Modify: `src/features/reviews/inline/index.ts`

- [ ] **Step 1: Add re-export for the store**

```typescript
// Add to existing exports:
export { useReviewModeStore } from '@/stores/reviewModeStore';
```

- [ ] **Step 2: Commit**

```bash
git add src/features/reviews/inline/index.ts
git commit -m "chore: re-export reviewModeStore from reviews barrel"
```

---

## Task 14: End-to-end verification

- [ ] **Step 1: TypeScript check**

```bash
npx tsc --noEmit
```

Expected: Clean.

- [ ] **Step 2: Lint check**

```bash
npm run lint
```

Expected: Clean (or only pre-existing warnings).

- [ ] **Step 3: Manual test flow**

1. Navigate to a completed Kaira Bot run detail
2. Click "Human Review" button
3. Verify: Report tab disappears, Logs/Delete/Visibility buttons slide out, breadcrumb "Runs" becomes inert, border glow appears, dirty bar slides up
4. Verify: Sherlock FAB is hidden
5. Click a thread row → thread detail opens, still in review mode
6. Override a verdict → dirty bar shows "1 unsaved change"
7. Navigate to Rules tab → override a rule status, add a note
8. Use left/right arrows → edits persist across threads
9. Click back to run detail → still in review mode, dirty bar shows accumulated changes
10. Click sidebar link → dirty modal appears
11. Click "Save Draft" → edits persist, BeforeAfterChips appear
12. Click "Finalize" → review exits, all elements reappear with smooth transition

- [ ] **Step 4: Final commit if any cleanup needed**

```bash
git add -A
git commit -m "chore: review universe — cleanup and polish"
```
