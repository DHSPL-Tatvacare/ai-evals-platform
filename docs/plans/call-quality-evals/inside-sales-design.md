# Inside Sales — Design Spec

**App ID:** `inside-sales`
**Display name:** Inside Sales
**Date:** 2026-03-24
**Mockups:** `.superpowers/brainstorm/16286-1774345560/`

---

## 1. Overview

Evaluate inside sales agent call performance using LLM judges. Agents make calls via LeadSquared (Ozonetel telephony). Call recordings (MP3) are on Ozonetel S3. The app ingests call data live from LSQ APIs, displays calls in a searchable listing, and runs rubric-based LLM evaluations on transcripts.

**Target users:** Sales ops, QA leads, team managers — reviewing human agent performance, not AI output.

**Difference from existing apps:** Voice Rx and Kaira evaluate AI agent output. Inside Sales evaluates human agent performance against structured scoring rubrics with per-dimension checks and compliance gates.

---

## 2. Component Reuse Policy

**Strict rule: reuse existing components. No duplicate components.** Every UI element must use the existing component stack. Only create new components when no existing component can serve the purpose. Below is the authoritative mapping.

### Existing components → Inside Sales usage

| Existing Component | Location | Inside Sales Usage |
|---|---|---|
| `WizardOverlay` | `src/features/evalRuns/components/WizardOverlay.tsx` | Eval wizard shell (6-step) |
| `RunInfoStep` | `src/features/evalRuns/components/RunInfoStep.tsx` | Wizard step 1 (run name + description) |
| `EvaluatorToggleStep` | `src/features/evalRuns/components/EvaluatorToggleStep.tsx` | Wizard step 4 — adapt for inside-sales evaluator picker |
| `LLMConfigStep` | `src/features/evalRuns/components/LLMConfigStep.tsx` | Wizard step 5 — provider/model/temp/thinking |
| `ParallelConfigSection` | `src/features/evalRuns/components/ParallelConfigSection.tsx` | Wizard step 5 — parallel workers |
| `ReviewStep` | `src/features/evalRuns/components/ReviewStep.tsx` | Wizard step 6 — summary banner + grouped details |
| `RunHeader` (in `VoiceRxRunDetail`) | `src/features/voiceRx/pages/VoiceRxRunDetail.tsx` | Run detail header — extract to shared if not already |
| `RunProgressBar` | `src/features/evalRuns/components/RunProgressBar.tsx` | Active run progress |
| `VerdictBadge` | `src/features/evalRuns/components/VerdictBadge.tsx` | Status badges everywhere |
| `DistributionBar` | `src/features/evalRuns/components/DistributionBar.tsx` | Score band + compliance distribution |
| `RunRowCard` | `src/features/evalRuns/components/RunRowCard.tsx` | Run list items |
| `RuleComplianceTab` | `src/features/evalRuns/components/threadReview/RuleComplianceTab.tsx` | Compliance tab in call drilldown |
| `SummaryBar` | `src/features/evalRuns/components/threadReview/SummaryBar.tsx` | Call drilldown summary boxes |
| `ReportTab` | `src/features/evalRuns/components/report/ReportTab.tsx` | Report tab in run detail |
| `OutputFieldRenderer` | `src/features/evalRuns/components/OutputFieldRenderer.tsx` | Evaluator output display |
| `CreateEvaluatorOverlay` | `src/features/evals/components/CreateEvaluatorOverlay.tsx` | Evaluator create/edit — extend for rubric builder |
| `EvaluatorCard` | `src/features/evals/components/EvaluatorCard.tsx` | Evaluator picker cards in wizard |
| `AudioPlayer` | `src/features/transcript/components/AudioPlayer.tsx` | Call playback (wavesurfer.js) |
| `TranscriptView` | `src/features/transcript/components/TranscriptView.tsx` | Adapt for diarized call transcript display |
| `EvaluationOverlay` | `src/features/evals/components/EvaluationOverlay.tsx` | Reference for transcription config UI patterns |
| `Tabs` | `src/components/ui/Tabs.tsx` | All tab bars |
| `Button` | `src/components/ui/Button.tsx` | All buttons |
| `EmptyState` | `src/components/ui/EmptyState.tsx` | All zero states |
| `Modal` / `ConfirmDialog` | `src/components/ui/Modal.tsx` | Delete confirmations |
| `Popover` | `src/components/ui/Popover.tsx` | Overflow menus, app switcher |
| `Skeleton` | `src/components/ui/Skeleton.tsx` | Loading states |
| `Alert` | `src/components/ui/Alert.tsx` | Error states |
| `MainLayout` | `src/components/layout/MainLayout.tsx` | App shell |
| `Sidebar` | `src/components/layout/Sidebar.tsx` | Extend with InsideSalesSidebarContent |
| `AppSwitcher` | `src/components/layout/AppSwitcher.tsx` | Add inside-sales to app list |
| `submitAndPollJob()` | `src/services/api/jobPolling.ts` | Wizard submission |
| `apiRequest` | `src/services/api/client.ts` | All HTTP calls |
| `notificationService` | `src/services/notifications/` | Toasts |
| `logger` | Logger utility | Diagnostics |
| `cn()` | `src/utils/cn.ts` | CSS class merging |
| `JobCompletionWatcher` | `src/components/JobCompletionWatcher.tsx` | Toast on eval completion |
| `Evaluator` model | `backend/app/models/evaluator.py` | `app_id="inside-sales"` |
| `EvalRun` + `ThreadEvaluation` models | `backend/app/models/eval_run.py` | `eval_type="call_quality"` |
| `Job` model + worker | `backend/app/services/job_worker.py` | `@register_job_handler("evaluate-inside-sales")` |
| LLM factory (`llm_base.py`) | `backend/app/services/evaluators/llm_base.py` | All LLM calls |
| `LoggingLLMWrapper` | `backend/app/services/evaluators/` | API call logging |
| Fork endpoint | `POST /api/evaluators/{id}/fork` | Evaluator forking |
| Seed defaults | `backend/app/services/seed_defaults.py` | Seed GoodFlip QA evaluator |
| Report generation | `backend/app/services/reports/` | New template, reuse pipeline |
| Auth + multi-tenancy | `backend/app/auth/` | Standard |
| `CamelModel` / `CamelORMModel` | `backend/app/schemas/base.py` | All new schemas |
| `TenantUserMixin` | `backend/app/models/base.py` | All new models |

### New components to create (only these)

| New Component | Purpose | Why existing doesn't suffice |
|---|---|---|
| `InsideSalesSidebarContent` | Nav-only sidebar (5 links, no item list) | Voice Rx/Kaira sidebars have scrollable item lists; this app needs nav-only |
| `CallListingPage` | Table with LSQ API pagination + filter panel overlay | No existing table-based listing page; Voice Rx uses sidebar-driven navigation |
| `CallFilterPanel` | Right-slide filter overlay (date, agent, direction, status, duration, score) | No existing filter panel component; this is the only new overlay |
| `SelectCallsStep` | Wizard step 2: LSQ API call selection with filters/stats/preview | Replaces `CsvUploadStep`; fundamentally different data source |
| `TranscriptionConfigStep` | Wizard step 3: language, script, model, diarization toggles | Adapted from `EvaluationOverlay` prerequisites tab; restructured as wizard step |
| `ScorecardTab` | Call drilldown: expandable dimensions with LLM critique + per-check evidence | New scoring format; `RuleComplianceTab` handles pass/fail, this handles scored dimensions with narrative |
| `InsideSalesRunResults` | Run detail results tab: stat cards + distributions + call table | Adapted from Kaira `RunDetail` results; different columns and metrics |
| `InsideSalesReportTemplate` | Backend: report generation template for call quality | New template; reuses report pipeline |
| `LSQClient` | Backend service: LSQ API pagination, rate limiting, lead hydration | New external API integration |
| `insideSalesStore` | Zustand store: calls, filters, pagination, selected calls | New app-specific state |
| `insideSalesRoutes` | Backend router: `/api/inside-sales/*` | New routes |

**No hardcoding.** All colors use CSS variables. All routes use `routes.ts` constants. All API calls go through `apiRequest`. All notifications through `notificationService`. All class merging through `cn()`.

---

## 3. Sidebar — Nav Only

No scrollable item list. No search bar. Five nav links:

| Nav Item | Icon (lucide) | Route | Description |
|----------|---------------|-------|-------------|
| Listing | `LayoutGrid` | `/inside-sales` | Call records table (LSQ API) |
| Evaluators | `FileText` | `/inside-sales/evaluators` | Scoring rubric management |
| Runs | `GitCompareArrows` | `/inside-sales/runs` | Evaluation run history |
| Dashboard | `LayoutDashboard` | `/inside-sales/dashboard` | Agent performance analytics |
| Logs | `FileText` | `/inside-sales/logs` | API call logs |

Plus Settings at sidebar bottom (shared pattern). User menu at bottom.

This departs from Voice Rx / Kaira which have scrollable item lists below nav links. Volume (683+ calls/day) makes a sidebar list impractical; the table listing handles all browsing.

---

## 4. Listing Page

### Layout hierarchy

1. **Page header:** h1 "Calls" + action buttons top-right
   - "Evaluate Selected" (primary, disabled until rows checked)
   - Overflow menu (⋮): Download Selected, Export CSV
2. **Tab bar:** "All Calls" (single tab, placeholder for future tabs)
3. **Search + filter toolbar:** inline search input + "Filters" button with active count badge + dismissible filter pills + "Clear all" link + result count
4. **Bulk action bar** (contextual, when rows selected): checkbox + count + "Deselect" link
5. **Table** with server-side pagination
6. **Pagination:** "Page X of Y · N calls"

### Data source & API flow

Table paginates directly against the LSQ API. No local sync/caching step. **2 API calls per page load:**

```
Frontend: GET /api/inside-sales/calls?page=1&pageSize=50&dateFrom=...&dateTo=...

Backend (LSQClient):
  1. POST LSQ RetrieveByActivityEvent (PageIndex=1, PageSize=50)
     → Returns 50 call activity records
     → Each has: agent name, phone, duration, recording URL, status, event code
     → Each has: RelatedProspectId (lead UUID) — but NOT the lead name

  2. Collect 50 RelatedProspectIds from step 1
     → Check in-memory cache: which IDs do we already have names for?
     → For uncached IDs (e.g. 30 of 50 on first load):
       GET LSQ Leads.GetByIds with those 30 IDs → returns 30 lead names
     → Cache all results (lead_id → name)
     → On repeat pages, cache hits more — second call shrinks or skips entirely

  3. Merge lead names into call records → return to frontend
```

**Default page:** today's date, 50 calls. 1 LSQ call for activities + 1 for lead names = 2 total. Fast.

**Rate limit (25 req/5s):** Not a concern at 2 calls per page. Only relevant during bulk eval wizard pagination — sequential and throttled.

**Lead cache:** In-memory dict on the backend process. No DB model needed. Agents call the same leads repeatedly so it warms fast. Cache lives for the process lifetime; cold-starts are cheap (one bulk lookup).

### Table columns

| Column | Source | Notes |
|--------|--------|-------|
| Date / Time | `mx_Custom_2` | Sortable, formatted |
| Agent | `CreatedByName` | Sortable, filterable |
| Lead | Hydrated from `RelatedProspectId` via bulk lookup + cache | Searchable |
| Phone | `DestinationNumber` from SourceData JSON | Mono font, formatted |
| Duration | `mx_Custom_3` (formatted mm:ss) | Sortable |
| Dir | Event code 21=In, 22=Out | Badge: blue "Out", purple "In" |
| Status | `Status` field | Badge: green "Answered", red "Missed" |
| Call Type | From activity event code (21/22 system + 204-241 custom) | Shows event name (Welcome Call, Assessment, etc.) |
| Eval | From eval_runs join | Badge: "Evaluated", "Pending", "In Progress" |
| Score | Overall eval score | Brand-purple badge |
| Actions | Play (inline) + overflow (⋮) | Play disabled for missed calls |

Row click → Call Detail drilldown page.

### Filter panel

Right-slide overlay (new `CallFilterPanel`, follows overlay pattern: `fixed inset-0 z-50`, backdrop blur, `w-[380px]`). Contains:

- Date range (from/to date inputs)
- Agent (multi-select dropdown with pills)
- Direction (checkbox: Outbound, Inbound)
- Call Status (checkbox: Answered, Missed)
- Call Type (dropdown: All, or specific event codes)
- Eval Status (dropdown: All, Evaluated, Pending, In Progress)
- Duration range (min/max inputs, seconds)
- Score range (min/max inputs)
- Footer: Reset + Apply buttons

Active filters show as dismissible pills below the toolbar.

### Call Detail (drilldown from table row)

Follows `ListingPage.tsx` pattern:

- Back button "Back to Calls"
- Page header: "Agent → Lead" + direction/status badges + "Evaluate" button + overflow menu
- Metadata grid: Date, Agent, Lead, Phone (mono), Duration, Score badge
- Audio player (reuse `AudioPlayer` component from `src/features/transcript/`)
- Tab bar (reuse `Tabs` component): Transcript / Scorecard

---

## 5. Evaluators Page

### Hub (table view)

1. **Page header:** h1 "Evaluators" + "Import CSV" button + "New Evaluator" primary button (reuse `Button`)
2. **Tab bar:** "All Evaluators" (reuse `Tabs`)
3. **Table:**

| Column | Description |
|--------|-------------|
| Name | Evaluator name, font-weight: 600 |
| Description | Truncated, text-secondary |
| Dimensions | Count |
| Total Pts | Sum of all dimension max points |
| Pass | Pass threshold score |
| Type | Badge (reuse `VerdictBadge` pattern): System (brand), Custom (grey), Forked (blue + git-fork icon) |
| Used In | Run count |
| Actions | Open (→) + overflow (⋮) |

Row click → Evaluator Detail drilldown.

### Detail (drilldown)

- Back button "Back to Evaluators"
- Page header: name + type badge + "Fork & Edit" button (for system evaluators, reuses existing fork endpoint) + "Edit" button (for own) + "Export CSV" + overflow menu
- Metadata bar: dimensions count, total pts, pass threshold, excellent threshold, compliance gate count, usage count
- Tab bar (reuse `Tabs`): **Scoring Criteria** / **Compliance & Thresholds**

**Scoring Criteria tab:** Dimension cards, each showing:
- Header: dimension name + point allocation (brand-purple badge)
- Check rows: check text + point value (mono, right-aligned)

**Compliance & Thresholds tab:**
- Compliance gates card (red-tinted): warning icon + gate text list
- Interpretation bands: 4 color-coded threshold cards (Strong, Good, Needs work, Poor)
- Operating principle text

### Create / Edit overlay

Extend existing `CreateEvaluatorOverlay` — add rubric builder mode for `app_id="inside-sales"`. Fields:

- Name (text input)
- Description (textarea)
- Pass / Excellent thresholds (two inputs)
- **Dimensions & Checks builder:**
  - Repeatable dimension blocks: name input + points input + trash icon (remove)
  - Within each: repeatable check rows: trash icon + name input + points input
  - "Add check" / "Add dimension" links
- **Compliance gates:** list of gate text inputs with warning icons + trash icons (remove). "Add gate" link.
- Footer: Cancel + Create/Save button

**Fork:** Reuses existing `POST /api/evaluators/{id}/fork` endpoint. Fork opens the edit overlay pre-populated.

**CSV Import:** Upload a CSV with columns mapping to dimensions/checks/points. Backend parses and creates evaluator.

### Data model

Reuses existing `Evaluator` model with `app_id="inside-sales"`. The evaluator's `prompt` contains the full rubric template. The `output_schema` contains dimension fields (type: number, with thresholds) plus compliance boolean fields.

**Seed:** GoodFlip Sales Call QA framework is seeded as a system evaluator (`tenant_id=SYSTEM_TENANT_ID`). Sales team creates additional evaluators through the create UI.

---

## 6. Evaluation Wizard

6-step `WizardOverlay` (reuse existing shell). Entry points:
- "Evaluate Selected" on Listing page (pre-populates step 2 with selected calls)
- "New" button in sidebar (starts fresh)
- "New Run" on Runs page

### Steps

**Step 1 — Run Info:** Reuse `RunInfoStep` component directly.

**Step 2 — Select Calls (new: `SelectCallsStep`):**
- Info callout: "Calls fetched live from LeadSquared"
- Date range (from/to)
- Agent dropdown + Direction dropdown
- Selection mode buttons: All Matching / Random Sample / Specific Calls
  - Random Sample: sample size input
  - Specific Calls: pre-selected from listing page checkboxes
- Toggles: Skip previously evaluated, Minimum duration (≥10s)
- Live stats: Matching → After Filters → Not Yet Evaluated
- Preview table (first 5 calls)

**Step 3 — Transcription (new: `TranscriptionConfigStep`, adapted from `EvaluationOverlay` prerequisites):**
- Stats: total, already transcribed, need transcription
- Language dropdown (Hindi, English, mixed, etc.)
- Source script (Auto-detect, Devanagari, Latin)
- Transcription model dropdown (Gemini 2.5 Flash, Pro, Whisper)
- Toggles: Force re-transcription, Preserve code-switching, Speaker diarization

**Step 4 — Evaluators:** Adapt `EvaluatorToggleStep` for inside-sales evaluator picker with cards showing dimension/pts/threshold.

**Step 5 — LLM Config:** Reuse `LLMConfigStep` + `ParallelConfigSection` directly. Add estimated workload display.

**Step 6 — Review:** Reuse `ReviewStep` component with sections: Call Selection, Transcription, Evaluators, Execution.

### Job submission

Submits `evaluate-inside-sales` job via `submitAndPollJob()`. Progress tracked by `jobTrackerStore`. Toast on completion via `JobCompletionWatcher`.

---

## 7. Run Detail

### Layout (exact Kaira `RunDetail` pattern)

1. **Breadcrumb:** Runs / runId
2. **RunHeader card** (reuse/extract from `VoiceRxRunDetail`): name + `VerdictBadge` + Logs/Delete buttons + metadata row
3. **Results / Report tabs** (reuse `Tabs`, same page)

### Results tab (new: `InsideSalesRunResults`)

- **3 stat cards** (reuse `StatCard` pattern): Calls (evaluated/total), Avg Score (/100), Compliance Pass (pass/total + violation count)
- **Side-by-side distribution bars** (reuse `DistributionBar`): Score Bands + Compliance
- **Search + filter chips** (same pattern as Kaira run detail)
- **Call results table:** Agent→Lead, Phone, Duration, Score, Compliance (pill badge), Completed (✓/✗)
- Row click → Call Drilldown

### Report tab

Reuse existing `ReportTab` component. New `InsideSalesReportTemplate` on backend generates:
- Score hero with grade circle
- Metric bars per dimension
- Executive summary prose
- Top Issues table (focus area + calls affected)
- Recommendations

Report generated as background job (`generate-report`), reusing existing report pipeline.

---

## 8. Call Drilldown (from Run Detail)

Follows exact `ThreadDetailV2` pattern:

1. **Breadcrumb:** Runs / runId / call name + timestamp
2. **Prev/next nav:** `< N/M >` buttons (same component pattern)
3. **Summary boxes** (reuse `SummaryBar` pattern, 4 horizontal): SCORE | VERDICT | COMPLIANCE | STATUS
4. **Split pane** (fills remaining height):
   - **Left (40%):** Transcript (adapt `TranscriptView` / `LinkedChatViewer` for diarized call format)
   - **Right (60%):** Tab bar (reuse `Tabs`) + tab content

### Tabs

**Scorecard tab (new: `ScorecardTab`):**
- Expandable dimension rows. Each shows:
  - Header: dimension name + score/max (color-coded) + chevron
  - Expanded detail:
    - **LLM critique narrative** — why the score was assigned, what was good/bad
    - **Per-check breakdown:** status dot (✓ pass / ~ partial / ✗ miss) + check name + **transcript evidence** (italic) + points awarded/max

**Compliance tab:** Reuse `RuleComplianceTab` directly with compliance gate data.
- Header: "COMPLIANCE — All N rules followed" (or "N violations")
- Table rows: status dot + rule_id + evidence text

---

## 9. Zero States

All reuse existing `EmptyState` component.

| Screen | Icon | Title | Description | CTA |
|--------|------|-------|-------------|-----|
| Listing — no calls | `Phone` | No calls found | No call records for selected date range and filters. | — |
| Listing — search no match | `Search` | No matching calls | Try a different search term or adjust filters. | — |
| Listing — API error | `AlertTriangle` | Failed to load calls | Could not connect to LeadSquared API. | Retry |
| Evaluators — empty | `FileText` | No evaluators yet | Create an evaluator to define scoring criteria. | Create Evaluator |
| Runs — empty | `GitCompareArrows` | No evaluation runs yet | Select calls from Listing and click Evaluate Selected. | — |
| Dashboard — no data | `LayoutDashboard` | No analytics data yet | Complete evaluation runs first. | — |

---

## 10. Resolved Questions

1. **S3 URL durability** — Not a concern. Ozonetel S3 URLs are permanent. No need to mirror MP3s.
2. **Hindi/regional transcription quality** — Already handled by the existing Voice Rx transcription pipeline. Plug it in faithfully (language selection, code-switching, diarization) and it works for Hindi/mixed calls.
3. **Lead bulk lookup** — Backend uses `GET /v2/Leads.svc/Leads.GetByIds` for batch hydration with an in-memory cache (`lead_id → name`). Agents call the same leads repeatedly, so cache warms fast. No DB model needed.
4. **Custom event codes** — Event codes 204-241 (Welcome Call, Assessment Call, etc.) are included. The listing table shows a "Call Type" column derived from the event code. Filters allow selecting specific call types.
5. **Rubric design** — GoodFlip Sales Call QA is seeded as a built-in system evaluator. Sales team creates additional evaluators through the Evaluators page create UI. No gating on this from engineering side.
