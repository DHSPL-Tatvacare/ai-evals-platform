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

## 2. Sidebar — Nav Only

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

## 3. Listing Page

### Layout hierarchy

1. **Page header:** h1 "Calls" + action buttons top-right
   - "Evaluate Selected" (primary, disabled until rows checked)
   - Overflow menu (⋮): Download Selected, Export CSV
2. **Tab bar:** "All Calls" (single tab, placeholder for future tabs)
3. **Search + filter toolbar:** inline search input + "Filters" button with active count badge + dismissible filter pills + "Clear all" link + result count
4. **Bulk action bar** (contextual, when rows selected): checkbox + count + "Deselect" link
5. **Table** with server-side pagination
6. **Pagination:** "Page X of Y · N calls"

### Data source

Table paginates directly against the LSQ API. No local sync/caching step. Backend proxies `POST /v2/ProspectActivity.svc/CustomActivity/RetrieveByActivityEvent` with filters mapped from frontend query params.

### Table columns

| Column | Source | Notes |
|--------|--------|-------|
| Date / Time | `mx_Custom_2` | Sortable, formatted |
| Agent | `CreatedByName` | Sortable, filterable |
| Lead | Hydrated from `RelatedProspectId` | Searchable |
| Phone | `DestinationNumber` from SourceData JSON | Mono font, formatted |
| Duration | `mx_Custom_3` (formatted mm:ss) | Sortable |
| Dir | Event code 21=In, 22=Out | Badge: blue "Out", purple "In" |
| Status | `Status` field | Badge: green "Answered", red "Missed" |
| Eval | From eval_runs join | Badge: "Evaluated", "Pending", "In Progress" |
| Score | Overall eval score | Brand-purple badge |
| Actions | Play (inline) + overflow (⋮) | Play disabled for missed calls |

Row click → Call Detail drilldown page.

### Filter panel

Right-slide overlay (matches `WizardOverlay` pattern: `fixed inset-0 z-50`, backdrop blur, `w-[380px]`). Contains:

- Date range (from/to date inputs)
- Agent (multi-select dropdown with pills)
- Direction (checkbox: Outbound, Inbound)
- Call Status (checkbox: Answered, Missed)
- Eval Status (dropdown: All, Evaluated, Pending, In Progress)
- Duration range (min/max inputs, seconds)
- Score range (min/max inputs)
- Footer: Reset + Apply buttons

Active filters show as dismissible pills below the toolbar.

### Call Detail (drilldown from table row)

Follows ListingPage.tsx pattern:

- Back button "Back to Calls"
- Page header: "Agent → Lead" + direction/status badges + "Evaluate" button + overflow menu
- Metadata grid: Date, Agent, Lead, Phone (mono), Duration, Score badge
- Audio player (wavesurfer.js, reuse existing `AudioPlayer` component)
- Tab bar: Transcript / Scorecard

---

## 4. Evaluators Page

### Hub (table view)

1. **Page header:** h1 "Evaluators" + "Import CSV" button + "New Evaluator" primary button
2. **Tab bar:** "All Evaluators"
3. **Table:**

| Column | Description |
|--------|-------------|
| Name | Evaluator name, font-weight: 600 |
| Description | Truncated, text-secondary |
| Dimensions | Count |
| Total Pts | Sum of all dimension max points |
| Pass | Pass threshold score |
| Type | Badge: System (brand), Custom (grey), Forked (blue + git-fork icon) |
| Used In | Run count |
| Actions | Open (→) + overflow (⋮) |

Row click → Evaluator Detail drilldown.

### Detail (drilldown)

- Back button "Back to Evaluators"
- Page header: name + type badge + "Fork & Edit" button (for system evaluators) + "Edit" button (for own) + "Export CSV" + overflow menu
- Metadata bar: dimensions count, total pts, pass threshold, excellent threshold, compliance gate count, usage count
- Tab bar: **Scoring Criteria** / **Compliance & Thresholds**

**Scoring Criteria tab:** Dimension cards, each showing:
- Header: dimension name + point allocation (brand-purple badge)
- Check rows: check text + point value (mono, right-aligned)

**Compliance & Thresholds tab:**
- Compliance gates card (red-tinted): warning icon + gate text list
- Interpretation bands: 4 color-coded threshold cards (Strong, Good, Needs work, Poor)
- Operating principle text

### Create / Edit overlay

Right-slide panel (matches `CreateEvaluatorOverlay` pattern). Fields:

- Name (text input)
- Description (textarea)
- Pass / Excellent thresholds (two inputs)
- **Dimensions & Checks builder:**
  - Repeatable dimension blocks: name input + points input + trash icon
  - Within each: repeatable check rows: trash icon + name input + points input
  - "Add check" / "Add dimension" links
- **Compliance gates:** list of gate text inputs with warning icons + trash icons. "Add gate" link.
- Footer: Cancel + Create/Save button

**Fork:** `POST /api/evaluators/{id}/fork` — copies all fields, sets `forked_from`, user owns the fork. Fork opens the edit overlay pre-populated.

**CSV Import:** Upload a CSV with columns mapping to dimensions/checks/points. Backend parses and creates evaluator.

### Data model

Evaluators use the existing `Evaluator` model with `app_id="inside-sales"`. The evaluator's `prompt` contains the full rubric template (dimensions, checks, scoring instructions). The `output_schema` contains dimension fields (type: number, with thresholds) plus compliance boolean fields.

Rubric structure (dimensions, checks, points, compliance gates, thresholds) is stored as structured JSON within the evaluator's config — NOT as a separate model. This reuses the existing evaluator infrastructure.

---

## 5. Evaluation Wizard

6-step `WizardOverlay` (900px, right-slide). Entry points:
- "Evaluate Selected" on Listing page (pre-populates step 2 with selected calls)
- "New" button in sidebar (starts fresh)
- "New Run" on Runs page

### Steps

**Step 1 — Run Info:**
- Run name (text)
- Description (optional textarea)

**Step 2 — Select Calls:**
- Info callout: "Calls fetched live from LeadSquared"
- Date range (from/to)
- Agent dropdown + Direction dropdown
- Selection mode buttons: All Matching / Random Sample / Specific Calls
  - Random Sample: sample size input
  - Specific Calls: pre-selected from listing page checkboxes
- Toggles: Skip previously evaluated, Minimum duration (≥10s)
- Live stats: Matching → After Filters → Not Yet Evaluated
- Preview table (first 5 calls)

**Step 3 — Transcription:**
- Stats: total, already transcribed, need transcription
- Language dropdown (Hindi, English, mixed, etc.)
- Source script (Auto-detect, Devanagari, Latin)
- Transcription model dropdown (Gemini 2.5 Flash, Pro, Whisper)
- Toggles: Force re-transcription, Preserve code-switching, Speaker diarization

**Step 4 — Evaluators:**
- Search input
- Evaluator picker cards (checkbox, name, type badge, meta: dimensions/pts/threshold)
- Selection summary: "N evaluators selected · Each call → N LLM judge calls"

**Step 5 — LLM Config:**
- Provider + Model dropdowns
- Temperature + Thinking level
- Parallel workers toggle + count input
- Estimated workload: calls, LLM calls, duration

**Step 6 — Review:**
- `ReviewStep` component (exact existing pattern):
  - Zone 1: Summary banner (name, description, rounded-full badge pills)
  - Zone 2: Grouped details card with dashed dividers between sections:
    - Call Selection (date range, direction, agent, selection, skip eval, min duration, total)
    - Transcription (already done, need, language, model, code-switching, diarization)
    - Evaluators (count, name, dimensions, compliance gates, LLM calls)
    - Execution (provider, model, temp, thinking, parallel, total LLM calls, est duration)
- "Start Evaluation" submit button

### Job submission

Submits `evaluate-inside-sales` job with params. Reuses existing `submitAndPollJob()` + `jobTrackerStore` for progress. Toast on completion via `JobCompletionWatcher`.

---

## 6. Run Detail

### Layout (exact Kaira `RunDetail` pattern)

1. **Breadcrumb:** Runs / runId
2. **RunHeader card:** name + Completed badge + Logs/Delete buttons + metadata row (ID mono, timestamp, duration, model, temperature)
3. **Results / Report tabs** (same page, same level)

### Results tab

- **3 stat cards:** Calls (evaluated/total), Avg Score (/100), Compliance Pass (pass/total + violation count)
- **Side-by-side distribution bars:** Score Bands (Strong/Good/Needs work/Poor with counts) + Compliance (Pass/Violation)
- **Search + filter chips:** All, Strong, Good, Needs work, Poor, Violation + call count
- **Call results table:** Agent→Lead, Phone, Duration, Score (bold), Compliance (pill badge), Completed (✓/✗)
- Row click → Call Drilldown

### Report tab

- **Score hero:** grade circle (A/B/C/D/F + color) + score/100 + metadata + Export PDF / Refresh buttons
- **Summary / Detailed Analysis tabs**
- **Summary tab:**
  - Metric bars (dimension label + percentage + colored mini-bar)
  - Executive summary prose block (LLM-generated narrative with bold highlights)
  - Top Issues table (colored dots + issue text + focus area + calls affected count)
- **Detailed Analysis tab:** (future — recommendations, agent breakdown, exemplars)

Report is generated as a background job (`generate-report`), reusing existing report infrastructure.

---

## 7. Call Drilldown (from Run Detail)

Follows exact `ThreadDetailV2` pattern:

1. **Breadcrumb:** Runs / runId / call name + timestamp
2. **Prev/next nav:** `< N/M >` buttons for navigating between calls in the run
3. **Summary boxes** (4 horizontal, bordered): SCORE | VERDICT | COMPLIANCE | STATUS
4. **Split pane** (fills remaining height):
   - **Left (40%):** Transcript with turn labels, speaker badges (Agent green, Lead grey), timestamps
   - **Right (60%):** Tab bar + tab content

### Tabs

**Scorecard tab (N dimensions):**
- Expandable dimension rows. Each shows:
  - Header: dimension name + score/max (color-coded) + chevron
  - Expanded detail:
    - **LLM critique narrative** — why the score was assigned, what was good/bad
    - **Per-check breakdown:** status dot (✓ pass green / ~ partial yellow / ✗ miss red) + check name + **transcript evidence** (italic, what the LLM observed in the call) + points awarded/max

**Compliance tab (N gates):**
- Exact `RuleComplianceTab` layout
- Header: "COMPLIANCE — All N rules followed" (or "N violations")
- Table rows: status dot (green ✓ or red ✗) + rule_id (colored by status) + evidence text

---

## 8. Zero States

All use the existing `EmptyState` component (`border-dashed`, icon circle, title, description, optional CTA button).

| Screen | Icon | Title | Description | CTA |
|--------|------|-------|-------------|-----|
| Listing — no calls | Phone | No calls found | No call records for selected date range and filters. Adjust filters or date. | — |
| Listing — search no match | Search | No matching calls | Try a different search term or adjust filters. | — |
| Listing — API error | AlertTriangle (red) | Failed to load calls | Could not connect to LeadSquared API. | Retry |
| Evaluators — empty | FileText | No evaluators yet | Create an evaluator to define scoring criteria. | Create Evaluator |
| Runs — empty | GitCompareArrows | No evaluation runs yet | Select calls from Listing and click Evaluate Selected. | — |
| Dashboard — no data | LayoutDashboard | No analytics data yet | Complete evaluation runs first. | — |

---

## 9. Platform Integration

### Reuse directly

| Component | Adaptation |
|-----------|-----------|
| `WizardOverlay` | Shell for eval wizard |
| `ReviewStep` | Review step content |
| `LLMConfigStep` | LLM config in wizard |
| `ParallelConfigSection` | Worker config |
| `EvalRun` + `ThreadEvaluation` models | `app_id="inside-sales"`, new `eval_type="call_quality"` |
| `Evaluator` model | `app_id="inside-sales"`, rubric stored in prompt/output_schema |
| Job worker + `@register_job_handler` | New `evaluate-inside-sales` handler |
| `AudioPlayer` (wavesurfer.js) | Reuse for call playback |
| `EmptyState` | All zero states |
| `VerdictBadge` | Status badges |
| `RuleComplianceTab` pattern | Compliance tab in call drilldown |
| `RunProgressBar` | Active run progress |
| `JobCompletionWatcher` | Toast on completion |
| `submitAndPollJob()` | Wizard submission |
| Report generation pipeline | New template for call eval report |
| Auth + multi-tenancy | Standard |
| LLM factory | Standard |

### Build new

| Component | Description |
|-----------|-------------|
| LSQ API client | Backend service: fetch call activities, paginate, rate-limit (25 req/5s) |
| Call listing route | `GET /api/inside-sales/calls` — proxies LSQ with filters |
| Call detail route | `GET /api/inside-sales/calls/:activityId` — single call with lead hydration |
| Evaluators page (hub + detail) | Table view, drilldown, create/edit overlay |
| Eval wizard step components | `SelectCallsStep`, `TranscriptionStep` (adapted from Voice Rx) |
| Scorecard tab with LLM critique | Dimension cards with expandable critique + per-check evidence |
| Run detail results tab | Stat cards, distribution bars, call table (adapted from Kaira) |
| Report template | Dimension performance, executive summary, top issues |
| Call Quality sidebar content | Nav-only (no item list) |
| Zustand store | `callQualityStore` for calls, filters, pagination state |

---

## 10. Open Questions (from overview, still valid)

1. **S3 URL durability** — Do Ozonetel recording URLs expire? Test with week-old URL.
2. **Hindi/regional transcription quality** — Verify Gemini quality for Hindi/mixed calls. May need Whisper fallback.
3. **Lead bulk lookup limits** — Test `GetByIds` with 100+ IDs for hydration.
4. **Custom event codes** — Should 204-241 (Welcome Call, Assessment Call, etc.) be ingested alongside 21/22?
5. **Rubric design** — GoodFlip Sales Call QA framework is the first evaluator. More rubrics need sales ops input.
