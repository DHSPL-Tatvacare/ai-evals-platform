# Phase 06 — Cleanup

## Files to Delete

1. **`src/features/evals/components/HumanEvalNotepad.tsx`** (724 lines)
   - Fully replaced by table-column approach
   - Remove import from `EvalsView.tsx` (line 10)
   - Remove from any barrel exports

2. **`src/services/export/exporters/correctionsExporter.ts`** (46 lines)
   - Human review data is now in backend, exportable via API if needed later
   - Check if anything imports this; if so, remove those imports

## Dead Code Removal

- **`src/types/eval.types.ts`**: Remove old `TranscriptCorrection` (lines 165-170), `HumanEvaluation` (lines 172-180), and `HumanEvalStatus` (line 3) if no longer referenced
- **`src/features/evals/components/EditDistanceBadge.tsx`**: Keep if used by other components, remove if only used by HumanEvalNotepad
- Check if `correctionsExporter` is referenced in any export barrel or menu — remove references

## Import Cleanup

- `EvalsView.tsx`: Remove `HumanEvalNotepad` import, add new imports
- Any file importing `HumanEvaluation` or `TranscriptCorrection` types: Update to new types
- Run `npx tsc -b` to find all broken imports after deletion

## Verification

- `npx tsc -b` — zero errors
- `npm run lint` — zero new warnings
- `grep -r "HumanEvalNotepad" src/` — zero results
- `grep -r "TranscriptCorrection" src/` — zero results (unless intentionally kept)
- `grep -r "correctionsExporter" src/` — zero results
- App loads, both tabs render, no console errors
