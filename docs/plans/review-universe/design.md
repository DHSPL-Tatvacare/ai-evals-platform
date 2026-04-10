# Review Universe — Design Spec

**Date:** 2026-04-10
**Status:** Approved
**Scope:** Human review mode as an isolated, immersive UI state within run detail

---

## Problem

The current human review implementation is fragmented:
- Review state lives in a React Context (`InlineReviewProvider`) that is local to a single page — navigating between run detail and thread detail loses state.
- No visual indication that the user is in a special mode — all tabs, buttons, and navigation remain active.
- Rule-level review in thread detail is not wired up despite the backend adapter (`build_kaira_items`) already producing `rule:{ruleId}` review items.
- BeforeAfterChips are not rendering for saved edits.
- The experience feels like editing a spreadsheet, not entering a focused review session.

## Solution

A "Review Universe" — when the user clicks Human Review, the page transitions into an immersive, contained state. Elements that don't serve the review are hidden, a persistent dirty bar anchors the bottom of the viewport, and a subtle border glow signals the mode. The user is locked in until they save or discard.

---

## Architecture

### Approach: Zustand Store + Layout Wrapper

A global `reviewModeStore` (Zustand) replaces the local React Context as the source of truth for review state. A `<ReviewUniverse>` layout wrapper, always mounted at the app shell level, renders the viewport-level chrome (border glow, dirty bar, navigation blocker). Individual pages read from the store to conditionally hide/show elements and render review controls.

The existing `InlineReviewProvider` becomes a thin compatibility shim that reads from the Zustand store, so existing components using `useInlineReview()` keep working without changes.

---

## Zustand Store: `reviewModeStore`

```typescript
interface ReviewModeState {
  // Core state
  active: boolean;
  runId: string | null;
  appId: AppId | null;
  reviewId: string | null;
  status: 'idle' | 'entering' | 'reviewing' | 'saving' | 'finalizing' | 'exiting';

  // Edits — keyed by `${itemKey}::${attributeKey}`
  edits: Record<string, InlineEditState>;
  baselineEdits: Record<string, InlineEditState>;
  notes: string;

  // Reviewable items (loaded from API on enter)
  reviewableItems: ReviewableItem[];

  // Derived (computed via selectors)
  // dirtyCount, dirtySummary, isDirty — computed by comparing edits vs baselineEdits

  // Actions
  enterReview: (runId: string, appId: AppId) => Promise<void>;
  updateAttribute: (itemKey: string, attrKey: string, patch: Partial<InlineEditState>) => void;
  acceptAttribute: (itemKey: string, attrKey: string) => void;
  correctAttribute: (itemKey: string, attrKey: string, newValue: string) => void;
  clearAttribute: (itemKey: string, attrKey: string) => void;
  setAttributeNote: (itemKey: string, attrKey: string, note: string) => void;
  saveDraft: () => Promise<void>;
  finalize: () => Promise<void>;
  discardDraft: () => Promise<void>;

  // Lookups
  getEdit: (itemKey: string, attrKey: string) => InlineEditState | undefined;
  isAttributeSaved: (itemKey: string, attrKey: string) => boolean;
}
```

### `enterReview(runId, appId)` flow:
1. Set `status: 'entering'`
2. Call `POST /api/reviews/runs/{runId}/draft` to create/get draft
3. Load reviewable items from API context
4. Populate `edits` and `baselineEdits` from draft items
5. Set `active: true`, `status: 'reviewing'`

### `saveDraft()` flow:
1. Set `status: 'saving'`
2. Build payload from `edits` (filter to items with decision !== '')
3. Call `PUT /api/reviews/{reviewId}` with payload
4. Update `baselineEdits = edits` (dirty count resets)
5. Set `status: 'reviewing'`
6. BeforeAfterChips now visible for saved attributes

### `finalize()` flow:
1. Set `status: 'finalizing'`
2. Build payload from `edits`
3. Call `POST /api/reviews/{reviewId}/finalize`
4. Set `status: 'exiting'` (triggers exit transition)
5. After transition completes: reset store to idle

### `discardDraft()` flow:
1. Show confirmation dialog
2. Call `DELETE /api/reviews/{reviewId}`
3. Set `status: 'exiting'` (triggers exit transition)
4. After transition completes: reset store to idle

---

## `<ReviewUniverse>` Layout Wrapper

Mounted at app shell level (in root layout / `Providers.tsx`). Always rendered, conditionally shows chrome.

### Renders (when `active === true`):

**1. Border glow overlay**
- `position: fixed`, `inset: 0`, `pointer-events: none`
- `box-shadow: inset 0 0 Xpx Ypx color-mix(in srgb, var(--color-brand-primary) 15%, transparent)`
- CSS animation: subtle 3s breathe cycle on shadow opacity (0.1 → 0.2 → 0.1)
- z-index: `var(--z-overlay)` minus 1 (below modals, above content)
- Elegant and subtle — not flashy

**2. Persistent dirty bar**
- `position: fixed`, `bottom: 0`, `left: 0`, `right: 0`
- `z-index: var(--z-sticky)`
- Content: change count with pulse indicator, Discard / Save Draft / Finalize buttons
- framer-motion: enters with `y: 60 → 0` (slide up), spring easing, 300ms
- framer-motion: exits with `y: 0 → 60` (slide down), 200ms
- Wrapped in `AnimatePresence` keyed on `active`

**3. Navigation blocker**
- Uses `react-router`'s `useBlocker` hook
- Blocks all navigation when `active === true` EXCEPT:
  - Run detail for the active `runId`: `/kaira/runs/{runId}`
  - Thread detail for threads in the active run: `/kaira/threads/{threadId}`
- Blocked navigation shows the dirty modal: "You have unsaved review changes" with Save Draft / Discard / Cancel options
- Sidebar links, breadcrumb "Runs" link, browser back/forward — all blocked
- `beforeunload` event also blocked (browser tab close)

---

## Page-Level Changes

### Run Detail — Review Mode Active

**Header:**
- Hidden (framer-motion exit): Visibility toggle, Human Review button, Logs button, Delete button
- Stays: Run title, status badge
- Animation: `opacity: 1→0, x: 0→20`, staggered 50ms, 200ms duration

**Breadcrumb:**
- "Runs" link → rendered as `<span>` (inert text, muted color)
- Run ID remains as text

**Tabs:**
- Report tab removed from tab array
- Results tab auto-selected, becomes the only tab
- `layout` prop on tab bar for smooth resize

**Thread table:**
- No changes — existing HUMAN REVIEW column stays
- Row clicks navigate to thread detail (within review universe)

### Thread Detail — Review Mode Active

**Header:**
- Start Review button — not rendered
- Left/right thread navigator (`< 2/5 >`) — stays, navigating between threads preserves all edits in the store (edits are keyed by itemKey, not by current thread)

**Verdict controls (Correctness, Efficiency, etc.):**
- Already wired via `InlineReviewControls` — now reads from Zustand store via the compatibility shim
- During live editing: dropdown to override value
- After save: BeforeAfterChip shown (original struck through → new value), dropdown still available to re-edit
- After finalize: BeforeAfterChip read-only

**Rules tab — NEW review integration:**
- Each rule row gets:
  - Status cell: becomes a `<Select>` dropdown when in review mode
    - Options: VIOLATED, FOLLOWED, NOT_APPLICABLE, NOT_EVALUATED
    - Default: current AI-assigned value
    - On change: calls `store.correctAttribute('rule:{ruleId}', 'status', newValue)`
  - New "Actions" column (rightmost):
    - Undo button: reverts to original value, calls `store.clearAttribute()`
    - Notes icon: opens note modal, calls `store.setAttributeNote()`
- Rule review items already exist in the backend adapter (`build_kaira_items` produces `rule:{ruleId}` attributes)

---

## Transitions (framer-motion)

### Entry transition (~500ms perceived):
1. **Hidden elements exit** — `AnimatePresence` wraps each hideable element. Exit: `opacity: 0, x: 20`, staggered 50ms between elements, 200ms duration each.
2. **Border glow fades in** — CSS transition on the overlay, 400ms ease-in.
3. **Dirty bar slides up** — `motion.div` with `initial={{ y: 60, opacity: 0 }}`, `animate={{ y: 0, opacity: 1 }}`, spring easing, 300ms.

### Exit transition (~400ms perceived):
1. **Dirty bar slides down** — `exit={{ y: 60, opacity: 0 }}`, 200ms.
2. **Border glow fades out** — CSS transition, 300ms.
3. **Hidden elements enter** — `AnimatePresence` enter: `opacity: 0→1, x: 20→0`, staggered 50ms, 200ms each.

### During navigation (run detail ↔ thread detail):
- No transition on the chrome (glow + dirty bar stay constant)
- Page content transitions via normal React Router behavior
- Dirty bar never unmounts

---

## Permissions

- `review:manage` permission gates all entry points
- Human Review button: only rendered if user has `review:manage` (existing `PermissionGate`)
- `enterReview()`: API call checks permission server-side; store shows error toast on 403
- Review controls in thread detail and rules tab: only rendered when `active && hasPermission`
- No new permissions needed

---

## BeforeAfterChips Behavior

| State | Verdict cells | Rules status cells |
|-------|--------------|-------------------|
| Live editing (unsaved) | Override dropdown, no chip | Override dropdown, no chip |
| After Save Draft | BeforeAfterChip (original → new) + dropdown to re-edit | BeforeAfterChip + dropdown |
| After Finalize | BeforeAfterChip read-only | BeforeAfterChip read-only |

Chip visibility is determined by `store.isAttributeSaved(itemKey, attrKey)` — returns true when the attribute exists in `baselineEdits` with a non-empty decision AND the value differs from original.

---

## Compatibility Shim

The existing `InlineReviewProvider` is refactored to be a thin wrapper:

```typescript
function InlineReviewProvider({ children }) {
  const store = useReviewModeStore();
  // Map store methods to the existing InlineReviewContextValue interface
  // Components using useInlineReview() keep working unchanged
  return <InlineReviewContext.Provider value={mappedValue}>{children}</InlineReviewContext.Provider>;
}
```

This means existing components (`InlineReviewControls`, `VerdictDropdown`, `InlineReviewBadge`) work without modification. Only the data source changes from local state → global store.

---

## Hidden / Visible Summary

### Hidden during review:
- Report tab
- Delete button
- Logs button
- Visibility toggle
- Sherlock FAB (ChatWidget)
- Start Review button
- Breadcrumb "Runs" link (becomes inert `<span>`)

### Visible during review:
- Run title + status badge
- Results tab (only tab)
- Thread table with drilldowns
- Thread detail with left/right thread navigation
- Review controls (verdicts in thread detail)
- Rule override controls (new, in Rules tab)
- Persistent dirty bar at viewport bottom
- Subtle border glow

---

## Dependencies

- `framer-motion` — for AnimatePresence, layout animations, entry/exit transitions (~15KB)
- Existing: `zustand`, `react-router-dom` (useBlocker), reviews API

---

## Files to Create / Modify

### New files:
- `src/stores/reviewModeStore.ts` — Zustand store
- `src/features/reviews/ReviewUniverse.tsx` — Layout wrapper (glow + dirty bar + nav blocker)
- `src/features/reviews/ReviewDirtyBar.tsx` — Persistent dirty bar component
- `src/features/reviews/ReviewBorderGlow.tsx` — Border glow overlay
- `src/features/reviews/ReviewNavigationBlocker.tsx` — Router blocker + dirty modal
- `src/features/reviews/RuleReviewControls.tsx` — Rule override dropdown + actions column

### Modified files:
- `src/app/Providers.tsx` or root layout — mount `<ReviewUniverse />`
- `src/features/reviews/inline/InlineReviewProvider.tsx` — refactor to read from store
- `src/features/evalRuns/pages/RunDetail.tsx` — conditional hide/show, framer-motion wrapping
- `src/features/evalRuns/pages/ThreadDetailV2.tsx` — remove start review button, wire rules tab
- `src/features/chat-widget/ChatWidget.tsx` — hide when review active
- `src/features/evalRuns/components/RunHeaderActions.tsx` — hide buttons when review active

### Unchanged:
- Backend — no changes needed, existing review API and adapters are sufficient
- `InlineReviewControls`, `VerdictDropdown`, `BeforeAfterChip`, `InlineReviewBadge` — work via compatibility shim
