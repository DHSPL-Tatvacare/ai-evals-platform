# Phase 03 — Table Extensions

## SegmentComparisonTable.tsx (Upload Flow)

### New props added to interface

```typescript
interface SegmentComparisonTableProps {
  // ... existing props unchanged ...
  /** When true, shows human review verdict column and enables editing */
  reviewMode?: boolean;
  /** Existing segment reviews (loaded from backend) */
  segmentReviews?: Map<number, SegmentReviewItem>;
  /** Callback when a segment verdict changes */
  onSegmentReviewChange?: (segmentIndex: number, review: SegmentReviewItem) => void;
}
```

### Grid change (line 818-area)

- Current: `grid-cols-[auto_80px_1fr_1fr_120px]`
- With reviewMode: `grid-cols-[auto_80px_1fr_1fr_120px_160px]`
- New 6th column: "Review" (160px) — contains verdict buttons + correction input

### SegmentRow changes

- New prop: `review?: SegmentReviewItem`, `onReviewChange?: (review: SegmentReviewItem) => void`, `reviewMode?: boolean`
- When `reviewMode=true`, render 6th column cell with:
  - Three icon buttons: Accept (check), Reject (x), Correct (edit) — pill style, active state highlighted
  - If verdict='correct': inline text input for correctedText (appears below buttons)
  - Small comment popover (optional, triggered by a note icon)
- When `reviewMode=false` and `review` exists: show read-only verdict badge (green/red/blue)
- When `reviewMode=false` and no `review`: show "—"

### Column header

- Add "Review" header to sticky row when `reviewMode` is true
- When `reviewMode` is false but `segmentReviews` has entries: show "Review" header read-only

### How verdict buttons work

```
[✓] [✗] [✎]  ← Accept / Reject / Correct
```

- Click Accept: `onSegmentReviewChange(idx, { segmentIndex: idx, verdict: 'accept' })`
- Click Reject: `onSegmentReviewChange(idx, { segmentIndex: idx, verdict: 'reject' })`
- Click Correct: Opens inline text input pre-filled with AI generated text. On blur/enter: `onSegmentReviewChange(idx, { segmentIndex: idx, verdict: 'correct', correctedText: value })`
- Active button gets colored bg (accept=success, reject=error, correct=info)

### Severity filter interaction

Works the same — filters segments, review column follows.

### Styling

Review column uses same border/bg patterns. Verdict badge colors: accept=success/10, reject=error/10, correct=info/10.

---

## ApiStructuredComparison.tsx (API Classic View)

### New props

```typescript
interface ApiStructuredComparisonProps {
  // ... existing ...
  reviewMode?: boolean;
  fieldReviews?: Map<string, FieldReviewItem>;
  onFieldReviewChange?: (fieldPath: string, review: FieldReviewItem) => void;
}
```

### Grid change

- Current: `grid-cols-[1fr_1.5fr_1.5fr_100px]`
- With reviewMode: `grid-cols-[1fr_1.5fr_1.5fr_100px_160px]`
- New 5th column: "Review"

### FieldRow changes

- Same pattern as SegmentRow: 3 verdict buttons, correction input for 'correct', comment popover
- `correctedValue` shown as text input when verdict='correct'
- Read-only badge when not in review mode

---

## SemanticAuditView.tsx (API Inspector View)

### Change to JudgeVerdictPane

- Add a "Human Review" section at the bottom of the verdict pane (below existing critique/evidence)
- When `reviewMode=true`: Accept/Reject/Correct buttons + correction input + comment textarea
- When review exists: show read-only verdict + any correction
- This is a small addition (~30 lines) to the existing pane, not a new component

### Props

```typescript
interface SemanticAuditViewProps {
  // ... existing ...
  reviewMode?: boolean;
  fieldReviews?: Map<string, FieldReviewItem>;
  onFieldReviewChange?: (fieldPath: string, review: FieldReviewItem) => void;
}
```

Pass review-related props through to JudgeVerdictPane for the currently selected field.

---

## ApiEvalsView.tsx (Orchestrator)

**Pass-through only** — receives reviewMode + fieldReviews + onFieldReviewChange from parent, passes to both SemanticAuditView and ApiStructuredComparison.

---

## Verification

- Visual: Review columns visible only when `reviewMode=true`
- Click verdict buttons → callback fires with correct data shape
- Correction text input appears on "Correct" → value captured
- Severity filter still works with review column present
- Grid alignment holds with 6th column (check at various viewport widths)
