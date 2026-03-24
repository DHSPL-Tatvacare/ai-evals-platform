# Phase 5: Inside Sales — Run Detail, Call Drilldown & Reports

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the run detail page (Results + Report tabs), the call drilldown with scorecard/compliance tabs, and the report generation template — completing the full evaluation review loop.

**Architecture:** Run detail reuses the Kaira `RunDetail` page hierarchy exactly: RunHeader card → Results/Report tabs. Results tab shows stat cards, distribution bars, filter chips, and a call results table. Call drilldown follows `ThreadDetailV2` exactly: breadcrumb, summary boxes, split pane (transcript left, tabs right). Report tab reuses `ReportTab` with a new backend template. The only new component is `ScorecardTab` for the expandable dimension critique view.

**Tech Stack:** Python (report template), TypeScript (React), existing `DistributionBar`, `VerdictBadge`, `RuleComplianceTab`, `ReportTab`, `SummaryBar`, `Tabs`, `AudioPlayer`.

**Branch:** `feat/phase-5-run-detail`

**Depends on:** Phase 4 (eval runs must exist to display).

---

## Background

After Phase 4, the database has `EvalRun` records with `eval_type="call_quality"` and `ThreadEvaluation` rows per call. Each `ThreadEvaluation.result` JSON contains:
- Dimension scores (number per dimension)
- Per-check scores with LLM critique text and transcript evidence
- Compliance gate results (boolean + evidence)
- Overall score and reasoning

This phase builds the UI to display these results and the report generation to summarize them.

## Key files to reference

- `docs/plans/call-quality-evals/inside-sales-design.md` — design spec sections 7 (Run Detail), 8 (Call Drilldown)
- `src/features/evalRuns/pages/RunDetail.tsx` — Kaira run detail (exact pattern to follow)
- `src/features/evalRuns/pages/ThreadDetailV2.tsx` — thread drilldown (exact pattern)
- `src/features/evalRuns/components/threadReview/SummaryBar.tsx` — summary boxes
- `src/features/evalRuns/components/threadReview/RuleComplianceTab.tsx` — compliance tab (reuse directly)
- `src/features/evalRuns/components/DistributionBar.tsx` — score distribution
- `src/features/evalRuns/components/report/ReportTab.tsx` — report tab with generation/display
- `src/features/voiceRx/pages/VoiceRxRunDetail.tsx` — RunHeader pattern, StatCard
- `backend/app/services/reports/` — report generation pipeline

## Guidelines

- **Follow Kaira RunDetail hierarchy exactly.** Same page structure, same component nesting, same tab positions.
- **ScorecardTab is the only new component.** Everything else is reused or adapted.
- **Report template** generates via the existing pipeline — new template, same infrastructure.

---

### Task 1: Build InsideSalesRunDetail page

**Files:**
- Replace: `src/features/insideSales/pages/InsideSalesRunDetail.tsx`

- [ ] **Step 1:** Read `src/features/evalRuns/pages/RunDetail.tsx` (Kaira) thoroughly. Note the exact hierarchy: breadcrumb → RunHeader → Results/Report tabs → conditional content.

- [ ] **Step 2:** Also read `src/features/voiceRx/pages/VoiceRxRunDetail.tsx` for the `RunHeader` component pattern (name, VerdictBadge, metadata row, Logs/Cancel/Delete buttons).

- [ ] **Step 3:** Build `InsideSalesRunDetail` following the same pattern:

**Structure:**
```
Breadcrumb: Runs / {runId}
RunHeader card:
  - Run name + VerdictBadge status
  - Metadata: ID (mono), timestamp, duration, model
  - Actions: Logs link, Cancel (if running), Delete
Results | Report tabs
  [Results tab content]
  [Report tab content]
```

- [ ] **Step 4:** Fetch run data via existing `fetchEvalRun(runId)` from `src/services/api/evalRunsApi.ts`. Poll while active using `usePoll`.

- [ ] **Step 5:** Show `RunProgressBar` when run is active (reuse directly).

- [ ] **Step 6:** Commit skeleton with RunHeader + tabs (empty tab content).

---

### Task 2: Build Results tab content

**Files:**
- Create: `src/features/insideSales/components/InsideSalesRunResults.tsx`

- [ ] **Step 1:** Read the Kaira RunDetail results section for the stat cards + distribution + table pattern.

- [ ] **Step 2:** Build:

**Stat cards (3, reuse StatCard pattern):**
- Calls: `{evaluated} / {total}`
- Avg Score: `{avg} / 100`
- Compliance Pass: `{pass} / {total}` + violation count subtitle

**Distribution bars (side-by-side, reuse `DistributionBar`):**
- Score Bands: Strong (80+) / Good (65-79) / Needs work (50-64) / Poor (<50)
- Compliance: Pass / Violation

**Filter bar:**
- Search input (match VoiceRxRunList pattern)
- Filter chips: All, Strong, Good, Needs work, Poor, Violation
- Call count

**Call results table:**
- Columns: Agent→Lead, Phone, Duration, Score (bold, color-coded), Compliance (pill badge), Completed (✓/✗)
- Row click → navigates to call drilldown

- [ ] **Step 3:** Fetch thread evaluations via existing `fetchRunThreads(runId)` API.

- [ ] **Step 4:** Commit.

---

### Task 3: Build Call Drilldown page

**Files:**
- Create: `src/features/insideSales/pages/InsideSalesCallDetail.tsx`

- [ ] **Step 1:** Read `ThreadDetailV2.tsx` closely. Follow the exact pattern:
  - Breadcrumb with Runs / runId / call name
  - Prev/next navigation (ChevronLeft/ChevronRight with counter)
  - Summary boxes (horizontal, bordered)
  - Split pane: left transcript, right tabs

- [ ] **Step 2:** Build:

**Summary boxes (reuse `SummaryBar` pattern or build 4 boxes):**
- SCORE: `{score}/100` (color-coded)
- VERDICT: pill badge (Strong/Good/Needs work/Poor)
- COMPLIANCE: pill badge (Pass/Violation)
- STATUS: ✓ Completed

**Split pane:**
- Left (40%): Call transcript with speaker diarization. Agent messages with green avatar + "Agent" badge. Lead messages with grey avatar + "Lead" badge. Turn numbers and timestamps.
- Right (60%): Tabs

**Tabs:**
- Scorecard (N) — Task 4
- Compliance (N) — reuse `RuleComplianceTab`

- [ ] **Step 3:** Fetch call data from `ThreadEvaluation.result` JSON. This contains all dimension scores, checks, critique, and compliance data.

- [ ] **Step 4:** Wire the prev/next navigation using sibling call IDs from the run. Follow the `ThreadDetailV2` pattern with `fetchRunThreads` + keyboard shortcuts (Alt+Left/Right).

- [ ] **Step 5:** Commit.

---

### Task 4: Build ScorecardTab component

**Files:**
- Create: `src/features/insideSales/components/ScorecardTab.tsx`

- [ ] **Step 1:** This is the only truly new component. It renders expandable dimension rows with LLM critique and per-check evidence.

- [ ] **Step 2:** Build:

**Each dimension row (collapsible):**
- **Header (always visible):** dimension name + progress bar (width = score/max %) + score/max (color-coded: green ≥70%, yellow ≥50%, red <50%) + chevron
- **Detail (expanded on click):**
  - **Critique text:** LLM narrative explaining the score (from `result.dimensions[key].critique`)
  - **Per-check rows:** Each check shows:
    - Status dot: ✓ green (full points), ~ yellow (partial), ✗ red (zero points)
    - Check name
    - Transcript evidence (italic, from `result.dimensions[key].checks[i].evidence`)
    - Points: `{awarded}/{max}` (mono, right-aligned)

**Total bar at bottom:** "Total Score" label + score/100 (brand color)

- [ ] **Step 3:** Data structure expected from `ThreadEvaluation.result`:
```typescript
interface CallEvalResult {
  overallScore: number;
  dimensions: Record<string, {
    score: number;
    maxScore: number;
    critique: string;
    checks: Array<{
      name: string;
      pointsAwarded: number;
      maxPoints: number;
      evidence: string;
    }>;
  }>;
  compliance: Record<string, {
    passed: boolean;
    evidence: string;
  }>;
  reasoning: string;
}
```

- [ ] **Step 4:** Use CSS variables for all colors. Use `cn()` for class merging. Dimension expand/collapse uses local state (not store).

- [ ] **Step 5:** Commit.

---

### Task 5: Wire Compliance tab

**Files:**
- Modify: `src/features/insideSales/pages/InsideSalesCallDetail.tsx`

- [ ] **Step 1:** Reuse `RuleComplianceTab` directly. Transform the call evaluation compliance data into the format `RuleComplianceTab` expects:

```typescript
const complianceRules: RuleCompliance[] = Object.entries(result.compliance).map(
  ([key, { passed, evidence }]) => ({
    rule_id: key,
    followed: passed,
    evidence,
    section: 'Compliance Gate',
  })
);
```

- [ ] **Step 2:** Pass to `RuleComplianceTab`:
```typescript
<RuleComplianceTab rules={complianceRules} sourceLabel="QA Framework" />
```

- [ ] **Step 3:** Commit.

---

### Task 6: Build report generation template (backend)

**Files:**
- Create: `backend/app/services/reports/inside_sales_template.py`
- Modify: `backend/app/services/reports/` (register template)

- [ ] **Step 1:** Read the existing report generation pipeline. Understand how report templates work and how they're dispatched by `generate-report` job handler.

- [ ] **Step 2:** Create the Inside Sales report template. It receives all `ThreadEvaluation` results for a run and generates:
  - **Score hero:** overall average, grade (A/B/C/D/F), call count, evaluator name
  - **Metric bars:** per-dimension average percentage
  - **Executive summary:** LLM-generated narrative (uses the existing report LLM call pattern)
  - **Top issues:** aggregated dimension failures sorted by frequency
  - **Recommendations:** LLM-generated coaching suggestions

- [ ] **Step 3:** The template should output the same `ReportPayload` structure that `ReportTab` expects. This ensures the existing `ReportTab` component works without modification.

- [ ] **Step 4:** Register the template so it's used when `app_id="inside-sales"`.

- [ ] **Step 5:** Test: generate a report for an existing run via the Report tab.

- [ ] **Step 6:** Commit.

---

### Task 7: Wire Report tab

**Files:**
- Modify: `src/features/insideSales/pages/InsideSalesRunDetail.tsx`

- [ ] **Step 1:** Import and render `ReportTab` in the Report tab slot. Pass the run ID. The component handles generation, polling, and display internally.

```typescript
<ReportTab runId={run.id} appId="inside-sales" />
```

- [ ] **Step 2:** The `ReportTab` component already supports:
  - Idle state with "Generate Report" CTA
  - Generation in progress with job polling
  - Report display with Summary / Detailed Analysis tabs
  - Export PDF + Refresh actions

If `ReportTab` needs an `appId` prop for template selection, add it.

- [ ] **Step 3:** Commit.

---

### Task 8: Wire Runs list page

**Files:**
- Replace: `src/features/insideSales/pages/InsideSalesRunList.tsx`

- [ ] **Step 1:** Read the Kaira `RunList.tsx` for the pattern: fetch eval runs filtered by `app_id`, render `RunRowCard` items, search + filter chips, pagination.

- [ ] **Step 2:** Adapt for Inside Sales:
  - Fetch runs: `fetchEvalRuns({ appId: 'inside-sales' })`
  - Use `RunRowCard` for each run (reuse directly)
  - Add Runs / Reports tabs (if implementing Reports tab at this stage)
  - Search by run name
  - Filter by status

- [ ] **Step 3:** Commit.

---

### Task 9: Verify and merge

- [ ] **Step 1:** Full checks:
```bash
npx tsc -b && npm run lint && npm run build
```

- [ ] **Step 2:** End-to-end test:
  - Submit an eval run from Phase 4
  - Navigate to Runs → click the completed run
  - Results tab: stat cards, distributions, call table all render
  - Click a call → drilldown: transcript left, scorecard right
  - Expand dimensions: critique + evidence render
  - Compliance tab: rules with pass/fail status
  - Report tab: generate report, verify it renders

- [ ] **Step 3:** Merge:
```bash
git checkout main && git merge feat/phase-5-run-detail
```
