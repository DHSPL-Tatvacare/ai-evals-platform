# Implementation Order & Dependency Map

## Execution Order (within each phase)

### Phase 1: Backend Pipeline (branch: `feat/vrx-refactor-phase1`)

```
1. Create flow_config.py                          [no deps]
2. Add NORMALIZATION_PROMPT_PLAIN constants        [no deps]
3. Extract _run_transcription()                    [depends on 1]
4. Extract _run_normalization()                    [depends on 1, 2]
   └── Includes _get_normalization_source()
   └── Includes _normalize_transcript()
5. Extract _run_critique()                         [depends on 1]
6. Extract _build_summary()                        [depends on 1]
   └── Includes _count_severity()
   └── Includes _extract_field_critiques_from_raw()
7. Rewrite run_voice_rx_evaluation()               [depends on 3-6]
   └── Replace if/else branches with FlowConfig + step calls
8. Test both flows manually                        [depends on 7]
```

**Phases 1+2 deploy atomically** — see OVERVIEW.md Deployment Strategy.

### Phase 2: Data Contract (branch: `feat/vrx-refactor-phase2`)

**Pre-requisite**: Delete old data before starting:
```sql
DELETE FROM api_logs;
DELETE FROM eval_runs WHERE eval_type = 'full_evaluation';
```

```
1. Rewrite eval.types.ts (FlowType, UnifiedCritique) [no deps]
2. DELETE extractFieldCritiques.ts                    [no deps]
3. Update VoiceRxRunDetail.tsx FullEvaluationDetail   [depends on 1]
   └── Includes new FieldCritiqueSection component
4. Update EvalsView.tsx flow dispatch                 [depends on 1]
5. Update SemanticAuditView.tsx                       [depends on 1]
6. Update ApiEvalsView.tsx                            [depends on 1]
7. Update SegmentComparisonTable.tsx prop type         [depends on 1]
8. Update eval_runs.py _run_to_dict()                 [no deps]
9. Test both flows in all views                       [depends on 3-8]
```

**Merge Phase 1+2 to main together. Then proceed to Phase 3.**

### Phase 3: Flow-Gated UI (branch: `feat/vrx-refactor-phase3`)

```
1. Backend: Add source_type filter to prompts route [no deps]
2. Backend: Add source_type filter to schemas route [no deps]
3. Frontend: promptsStore sourceType filtering      [no deps]
4. Frontend: schemasStore sourceType filtering      [no deps]
5. EvaluationOverlay: filter prompt dropdowns       [depends on 3]
6. EvaluationOverlay: tag new prompts with sourceType [depends on 5]
7. PromptsTab: group by flow                        [depends on 3]
8. SchemasTab: group by flow                        [depends on 4]
9. Verify seed_defaults source_type tags            [no deps]
10. Test all filtering                              [depends on 1-9]
```

**Merge to main before Phase 4.**

### Phase 4: Hardening (branch: `feat/vrx-refactor-phase4`)

```
1. Backend: Listing sourceType immutability         [no deps]
2. Backend: _validate_pipeline_inputs()             [no deps]
3. Backend: PipelineStepError + per-step try/except [depends on 2]
4. Backend: Normalization non-fatal error handling   [depends on 3]
5. Frontend: ListingPage cross-flow action hiding   [no deps]
6. Frontend: Step-specific error display            [depends on 3]
7. Frontend: Warning display for normalization      [depends on 4]
8. Frontend: Flow badge on listing/run pages        [no deps]
9. Full regression test                             [depends on all]
```

## Risk Assessment

| Phase | Risk | Mitigation |
|-------|------|------------|
| 1 | Changes core execution — could break both flows | Two-commit strategy: first commit adds step functions (additive, no breakage), second commit rewires main function (swap). Easier to bisect. |
| 1→2 | Deployment gap: new backend shape + old frontend = broken display | Ship Phases 1+2 atomically. Wipe data once before the combined deploy. |
| 3 | Filtering could hide prompts users expect to see | Include `sourceType=null` (untagged) in all filter results. This is the escape hatch. |
| 4 | Immutability enforcement might break existing workflows | Only enforce on non-pending listings. Pending → any flow is always allowed. |

## What NOT to Change

- **response_parser.py** — Parsers stay as-is. Output normalization happens in the step functions. Avoids breaking the parsers for other callers.
- **prompt_resolver.py** — No changes. It already reads `use_segments` from the context dict. The caller sets this from `flow.use_segments_in_prompts`.
- **Custom evaluator runner** — Completely separate pipeline, not affected by this refactor.
- **Batch runner / Adversarial runner** — Different app (kaira-bot), not affected.
- **Job worker dispatch** — The registered handler name stays `evaluate-voice-rx`. No routing changes.

## Success Criteria

After all 4 phases:

1. Upload flow eval produces `result.critique.flowType: "upload"` with segments
2. API flow eval produces `result.critique.flowType: "api"` with fieldCritiques
3. Both flows support normalization (language toggle appears in Semantic Audit)
4. Prompt dropdowns show only flow-relevant items
5. Schema dropdowns show only flow-relevant items
6. New prompts/schemas auto-tagged with sourceType
7. Listing sourceType locked after first data acquisition
8. Cross-flow actions disabled on committed listings
9. Step-specific errors displayed with failed step name
10. Normalization failure is non-fatal (warning, not error)
11. All evaluation tables render correct data for correct flow (no cross-contamination)
12. No references to `apiCritique`, `llmTranscript`, or `extractFieldCritiques` remain in codebase
