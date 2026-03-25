# Phase 6 — Polish, Caching & Integration

## Objective

Harden the report system for production: add caching to avoid repeated LLM calls, handle edge cases and error states, add loading UX, update project docs, and ensure the report works gracefully across all run states.

## Pre-flight

- Branch: `feat/report-phase-6-polish` from `main` (Phase 5 merged)
- All phases functional — this is hardening, not new features

---

## Step 1: Report Caching

### Problem
Narrative generation takes 10-30s and costs ~$0.01-0.03 per call. Users will click the Report tab multiple times. The underlying data doesn't change after a run completes.

### Solution: Cache the full ReportPayload on the EvalRun row.

#### Backend: Add `report_cache` column

In `backend/app/models/eval_run.py`, add to the `EvalRun` model:
```python
report_cache = Column(JSON, nullable=True, default=None)
```

**No migration needed** — the startup `create_all()` handles schema changes for new nullable columns. If it doesn't auto-add, add an explicit `ALTER TABLE` in the startup sequence (follow existing patterns like `source_type` column addition).

#### Backend: Cache logic in ReportService

```python
async def generate(self, run_id: str, force_refresh: bool = False) -> ReportPayload:
    run = await self._load_run(run_id)

    # Check cache first (unless force refresh)
    if not force_refresh and run.report_cache:
        try:
            return ReportPayload.model_validate(run.report_cache)
        except Exception:
            pass  # Cache corrupted, regenerate

    # ... full generation pipeline ...

    # Cache the result
    await self._save_cache(run.id, payload)
    return payload

async def _save_cache(self, run_id: str, payload: ReportPayload) -> None:
    """Persist report payload to eval_run.report_cache."""
    stmt = (
        update(EvalRun)
        .where(EvalRun.id == run_id)
        .values(report_cache=payload.model_dump())
    )
    await self.db.execute(stmt)
    await self.db.commit()
```

#### API: Add `refresh` query param

```python
@router.get("/{run_id}")
async def get_report(
    run_id: str,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    service = ReportService(db)
    return await service.generate(run_id, force_refresh=refresh)
```

#### Frontend: Refresh button

Add a "Regenerate" button next to "Export PDF" that calls with `?refresh=true`:

```typescript
const handleRefresh = async () => {
  setLoading(true);
  try {
    const freshReport = await reportsApi.fetchReport(runId, { refresh: true });
    setReport(freshReport);
    notificationService.success('Report regenerated');
  } catch (err) {
    notificationService.error('Failed to regenerate report');
  } finally {
    setLoading(false);
  }
};
```

Update `reportsApi.ts`:
```typescript
fetchReport: (runId: string, opts?: { refresh?: boolean }): Promise<ReportPayload> =>
  apiRequest<ReportPayload>(
    `/api/reports/${runId}${opts?.refresh ? '?refresh=true' : ''}`
  ),
```

---

## Step 2: Edge Cases & Error Handling

### Runs that shouldn't have reports

Not all eval runs should show the Report tab. Guard conditions:

```typescript
// In RunDetail.tsx — only show Report tab when:
const canShowReport =
  run.evalType === 'batch_thread' &&
  ['completed', 'completed_with_errors'].includes(run.status) &&
  (run.summary?.completed ?? 0) >= 1;
```

### Runs with zero threads completed

Backend should return a valid but minimal report:
```python
if not threads:
    # Return a stub report — health score F, empty sections
    return ReportPayload(
        metadata=metadata,
        health_score=HealthScore(grade="F", numeric=0, breakdown=...),
        distributions=VerdictDistributions(
            correctness={}, efficiency={}, adversarial=None,
            intent_histogram=IntentHistogram(buckets=[], counts=[]),
            custom_evaluations={},
        ),
        rule_compliance=RuleComplianceMatrix(rules=[], co_failures=[]),
        friction=FrictionAnalysis(
            total_friction_turns=0, by_cause={}, recovery_quality={},
            avg_turns_by_verdict={}, top_patterns=[],
        ),
        adversarial=None,
        exemplars=Exemplars(best=[], worst=[]),
        production_prompts=ProductionPrompts(intent_classification=None, meal_summary_spec=None),
        narrative=None,
    )
```

### Missing evaluator data

Some runs skip certain evaluators (e.g., intent disabled). Handle gracefully:
- `intent_accuracy: null` → excluded from health score (remaining weights redistribute)
- Empty correctness_verdicts → correctness_rate = 0
- Missing efficiency → efficiency_rate = 0

Update health score to handle partial data:
```python
def compute_health_score(...):
    active_metrics = {}
    if avg_intent_accuracy is not None:
        active_metrics["intent"] = avg_intent_accuracy * 100
    if correctness_verdicts:
        active_metrics["correctness"] = (correctness_verdicts.get("PASS", 0) / max(total, 1)) * 100
    # ... etc

    if not active_metrics:
        return HealthScore(grade="N/A", numeric=0, breakdown=...)

    # Equal weight among active metrics
    weight = 1.0 / len(active_metrics)
    numeric = sum(v * weight for v in active_metrics.values())
    # ... grade calculation
```

### LLM provider not configured

If `get_llm_provider()` fails (no settings for app), narrative is None. Frontend already handles this with placeholder text. No additional work needed.

### Very large runs (1000+ threads)

- Aggregation: O(N) traversal, fine up to 10K threads
- Exemplar selection: sorts all threads, fine up to 10K
- Narrative prompt: only includes top 5 best + worst transcripts (bounded)
- PDF: only renders 10 exemplars (5+5), chart data is aggregated → bounded
- No special handling needed for v1

---

## Step 3: Loading & UX States

### ReportTab loading states:

```
STATE           UI
──────────────  ──────────────────────────────────────────────
initial         Skeleton placeholders (metric cards + section outlines)
loading         Skeleton with pulse animation
                "Generating report... This may take up to 30 seconds"
                (show after 3s delay to avoid flash)
error           CalloutBox (danger): error message + retry button
loaded          Full report rendered
exporting       "Export PDF" button shows spinner, disabled
refreshing      Overlay dimming current report + spinner
```

### Skeleton design:
```typescript
const ReportSkeleton = () => (
  <div className="space-y-8 max-w-[900px] mx-auto animate-pulse">
    {/* Metric cards */}
    <div className="grid grid-cols-4 gap-4">
      {[1,2,3,4].map(i => (
        <div key={i} className="h-24 bg-[var(--bg-secondary)] rounded-lg" />
      ))}
    </div>
    {/* AI assessment */}
    <div className="h-32 bg-[var(--bg-secondary)] rounded-lg" />
    {/* Charts placeholder */}
    <div className="grid grid-cols-2 gap-4">
      <div className="h-48 bg-[var(--bg-secondary)] rounded-lg" />
      <div className="h-48 bg-[var(--bg-secondary)] rounded-lg" />
    </div>
    {/* Table placeholder */}
    <div className="h-64 bg-[var(--bg-secondary)] rounded-lg" />
  </div>
);
```

---

## Step 4: Update Project Documentation

### Update CLAUDE.md:

Add to "API routers registered" count: 16 (was 15, add reports).

Add to relevant sections:
```
- Report system: `backend/app/services/reports/` — aggregation, AI narrative, health score.
- Report API: `GET /api/reports/{run_id}` — returns full `ReportPayload`.
- Report caching: `EvalRun.report_cache` column stores serialized payload.
- Report frontend: `src/features/evalRuns/components/report/` — on-screen + PDF export.
- Production prompts: `backend/app/services/reports/prompts/production_prompts.py` (static, Kaira-only).
```

### Update MEMORY.md:

Add entry for report system:
```
## Report System
- Backend: `backend/app/services/reports/` (report_service, aggregator, narrator, health_score, schemas)
- Frontend: `src/features/evalRuns/components/report/` (ReportTab + 8 section components)
- PDF export: `src/features/evalRuns/export/reportPdfExporter.ts`
- API: `GET /api/reports/{run_id}` (cached in EvalRun.report_cache)
- Health score: equal weights (25% each) across intent, correctness, efficiency, task completion
- AI narrative: via existing llm_base.py, generates structured JSON (executive summary, issues, gaps, recommendations)
- Production prompts: static constants in production_prompts.py (Kaira intent + meal summary)
```

---

## Step 5: Run Status Awareness

### Auto-show Report tab after run completes

If the user is viewing RunDetail while a run is in progress, and the run completes, the Report tab should appear in the tab bar automatically.

This already works if RunDetail re-renders on run status change (it does — it polls the job). Just ensure the tab condition re-evaluates:

```typescript
// The existing poll-based re-fetch of run data already triggers re-render
// The tab condition `run.status === 'completed'` will naturally show the tab
// No additional work needed
```

### Cache invalidation

Report cache is write-once per run. No invalidation needed because:
- Completed runs don't change (data is immutable)
- `?refresh=true` explicitly bypasses cache
- If a new evaluator is added and the run re-evaluated, it creates a NEW run (new run_id) → no stale cache

---

## Step 6: Accessibility

- All chart images in PDF should have alt-text equivalents (tables/numbers alongside charts)
- On-screen charts: Recharts includes ARIA labels by default
- Color contrast: all text meets WCAG AA against backgrounds (the design token colors are AA-compliant)
- Keyboard navigation: Report tab is focusable, export button has proper focus styles

---

## Verification Checklist (Full System)

### Backend
- [ ] `GET /api/reports/{run_id}` returns complete payload for a real run
- [ ] Second call returns cached response (fast, no LLM call)
- [ ] `?refresh=true` regenerates and updates cache
- [ ] Report for run with 0 completed threads returns valid stub
- [ ] Report for run with no adversarial data returns `adversarial: null`
- [ ] Report for run with disabled evaluators handles missing metrics
- [ ] `report_cache` column exists on eval_runs table
- [ ] 404 returned for non-existent run ID

### Frontend — On-screen
- [ ] Report tab appears only for completed batch_thread runs
- [ ] Loading skeleton shown during fetch
- [ ] All 8 sections render with real data
- [ ] Charts render correctly in all sections
- [ ] Exemplar transcripts show chat bubbles with proper styling
- [ ] Sections with null narrative show placeholders
- [ ] Refresh button regenerates report
- [ ] Error state shows retry button
- [ ] No TypeScript errors (`npx tsc -b`)
- [ ] No lint errors (`npm run lint`)

### Frontend — PDF
- [ ] Export button generates downloadable PDF
- [ ] PDF has cover page with health score
- [ ] PDF has all sections matching on-screen view
- [ ] Charts captured as clear images (no CSS variable artifacts)
- [ ] Tables have alternating rows, colored cells
- [ ] Callout boxes render with borders and backgrounds
- [ ] No text overflow — all content wraps within margins
- [ ] Page breaks don't split elements mid-card
- [ ] Headers and footers on all pages (except cover)
- [ ] File size < 2MB
- [ ] Loads correctly in Chrome, Preview, Adobe Reader

### Integration
- [ ] Report doesn't break existing RunDetail functionality
- [ ] No new console errors during flow
- [ ] CLAUDE.md router count updated
- [ ] Docker build succeeds with all changes

---

## Future Enhancements (Out of Scope for v1)

These are noted for roadmap, NOT for implementation now:

1. **Multi-run comparison reports** — aggregate across N runs, show trends
2. **Scheduled report generation** — auto-generate after every batch run completes
3. **Email delivery** — send PDF to configured recipients
4. **Voice Rx reports** — extend production_prompts and aggregator for voice-rx app
5. **Report history** — store multiple cached reports per run (version history)
6. **Interactive PDF** — PDF with clickable links to threads in the platform
7. **Custom weights** — allow users to configure health score weights per app
8. **Trend overlay** — show how metrics changed vs. previous run in the same report
