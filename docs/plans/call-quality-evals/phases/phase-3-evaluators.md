# Phase 3: Inside Sales — Evaluators Page

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Evaluators management page — table hub, detail drilldown, create/edit overlay with rubric builder, fork functionality, CSV import, and seed the GoodFlip Sales Call QA as a built-in system evaluator.

**Architecture:** Reuses the existing `Evaluator` model (`app_id="inside-sales"`). Rubric structure (dimensions, checks, points, compliance gates, thresholds) is stored in the evaluator's `output_schema` as structured JSON. The UI extends `CreateEvaluatorOverlay` with a rubric builder mode. System evaluators are seeded via `seed_defaults.py`.

**Tech Stack:** Python (FastAPI, SQLAlchemy), TypeScript (React, Zustand), existing evaluator components.

**Branch:** `feat/phase-3-evaluators`

**Depends on:** Phase 1 (app shell). Does NOT depend on Phase 2 (listing) — can run in parallel.

---

## Background

The existing `Evaluator` model has: `name`, `prompt`, `output_schema` (JSON list), `is_global`, `forked_from`, `app_id`. For Inside Sales, the rubric maps onto this:

- `prompt` → full rubric template with dimension instructions for the LLM judge
- `output_schema` → dimension fields (type: number, thresholds) + compliance booleans + reasoning text
- `forked_from` → enables fork & edit of system evaluators

The existing fork endpoint (`POST /api/evaluators/{id}/fork`), create, update, and delete endpoints all work. The frontend needs a rubric-aware create/edit overlay and a new Evaluators page.

## Key files to reference

- `docs/plans/call-quality-evals/inside-sales-design.md` — design spec section 5 (Evaluators)
- `docs/plans/call-quality-evals/overview.md` — GoodFlip QA framework structure (also available as PDF)
- `backend/app/models/evaluator.py` — `Evaluator` ORM model
- `backend/app/schemas/evaluator.py` — `EvaluatorCreate`, `EvaluatorUpdate`, `EvaluatorResponse`
- `backend/app/routes/evaluators.py` — existing CRUD + fork + seed endpoints
- `backend/app/services/seed_defaults.py` — seed pattern for system evaluators
- `src/features/evals/components/CreateEvaluatorOverlay.tsx` — existing create/edit overlay
- `src/features/evals/components/EvaluatorCard.tsx` — card display with fork/global badges

## Guidelines

- **Reuse existing evaluator endpoints.** All CRUD operations go through `/api/evaluators`. No new backend routes needed for evaluators themselves.
- **Extend, don't duplicate, the CreateEvaluatorOverlay.** Add a rubric builder mode that activates for `app_id="inside-sales"`.
- **GoodFlip QA evaluator** is seeded as system data (`SYSTEM_TENANT_ID`). Read-only to all tenants. Users fork to customize.

---

### Task 1: Seed GoodFlip Sales Call QA evaluator

**Files:**
- Modify: `backend/app/services/seed_defaults.py`

- [ ] **Step 1:** Read the existing kaira-bot evaluator seed pattern in `seed_defaults.py` (search for `"kaira-bot"` evaluators). Follow the same idempotent pattern.

- [ ] **Step 2:** Add an `_seed_inside_sales_evaluators()` function. The GoodFlip QA evaluator has:
  - 10 scored dimensions (output_schema fields, type: number)
  - 3 compliance gates (output_schema fields, type: boolean)
  - 1 overall_score (isMainMetric: true)
  - 1 reasoning field (hidden)
  - Prompt: full rubric with dimension descriptions and scoring instructions

- [ ] **Step 3:** The `output_schema` for GoodFlip QA should follow the existing pattern:

```python
GOODFLIP_QA_SCHEMA = [
    {"key": "overall_score", "type": "number", "description": "Total score out of 100", "displayMode": "header", "isMainMetric": True, "thresholds": {"green": 80, "yellow": 65}},
    {"key": "call_opening", "type": "number", "description": "Call Opening & Permission (max 10)", "displayMode": "card", "isMainMetric": False, "thresholds": {"green": 8, "yellow": 5}},
    {"key": "brand_positioning", "type": "number", "description": "Brand Positioning & Promise (max 15)", "displayMode": "card", "isMainMetric": False, "thresholds": {"green": 12, "yellow": 8}},
    {"key": "metabolism_explanation", "type": "number", "description": "Metabolism Explanation (max 15)", "displayMode": "card", "isMainMetric": False, "thresholds": {"green": 12, "yellow": 8}},
    {"key": "metabolic_score_explanation", "type": "number", "description": "Metabolic Score Explanation (max 10)", "displayMode": "card", "isMainMetric": False, "thresholds": {"green": 8, "yellow": 5}},
    {"key": "credibility_safety", "type": "number", "description": "Credibility, Boundaries & Safety (max 10)", "displayMode": "card", "isMainMetric": False, "thresholds": {"green": 8, "yellow": 5}},
    {"key": "transition_probing", "type": "number", "description": "Transition to Probing (max 5)", "displayMode": "card", "isMainMetric": False, "thresholds": {"green": 4, "yellow": 3}},
    {"key": "probing_quality", "type": "number", "description": "Probing Quality (max 15)", "displayMode": "card", "isMainMetric": False, "thresholds": {"green": 12, "yellow": 8}},
    {"key": "intent_decision_mapping", "type": "number", "description": "Intent & Decision Mapping (max 10)", "displayMode": "card", "isMainMetric": False, "thresholds": {"green": 8, "yellow": 5}},
    {"key": "program_mapping", "type": "number", "description": "Program Mapping & Next Step (max 10)", "displayMode": "card", "isMainMetric": False, "thresholds": {"green": 8, "yellow": 5}},
    {"key": "closing_impression", "type": "number", "description": "Closing & Brand Impression (max 5)", "displayMode": "card", "isMainMetric": False, "thresholds": {"green": 4, "yellow": 3}},
    {"key": "compliance_no_misinformation", "type": "boolean", "description": "No medical misinformation", "displayMode": "card", "isMainMetric": False},
    {"key": "compliance_no_stop_medicines", "type": "boolean", "description": "No advice to stop prescribed medicines", "displayMode": "card", "isMainMetric": False},
    {"key": "compliance_no_guarantees", "type": "boolean", "description": "No guaranteed or fear-based outcome claims", "displayMode": "card", "isMainMetric": False},
    {"key": "reasoning", "type": "text", "description": "Detailed critique per dimension with evidence", "displayMode": "hidden", "isMainMetric": False, "role": "reasoning"},
]
```

- [ ] **Step 4:** The prompt should instruct the LLM judge on how to score each dimension. Reference `docs/plans/call-quality-evals/overview.md` for the full GoodFlip QA framework text. Include dimension descriptions, check items with point values, compliance gates, and the scoring interpretation guide. Use `{{transcript}}` as the variable for the call transcript.

- [ ] **Step 5:** Call the seed function from `seed_all_defaults()`. Follow the idempotent pattern: check if evaluator with this name + `SYSTEM_TENANT_ID` + `app_id="inside-sales"` already exists before inserting.

- [ ] **Step 6:** Test by restarting the backend and verifying the evaluator appears via API:
```bash
curl http://localhost:8721/api/evaluators?appId=inside-sales
```

- [ ] **Step 7:** Commit:
```bash
git add backend/app/services/seed_defaults.py
git commit -m "feat: seed GoodFlip Sales Call QA evaluator for inside-sales"
```

---

### Task 2: Build Evaluators hub page (table view)

**Files:**
- Replace: `src/features/insideSales/pages/InsideSalesEvaluators.tsx`
- Create: `src/features/insideSales/components/EvaluatorTable.tsx`

- [ ] **Step 1:** Read design spec section 5 (Evaluators) for the table layout.

- [ ] **Step 2:** Build the page. It fetches evaluators via `apiRequest('/api/evaluators?appId=inside-sales')` and renders a table. Use the existing evaluators API — no new backend routes.

Table columns: Name (bold), Description (truncated), Dimensions (count from output_schema number fields), Total Pts (sum of max points), Pass (from config), Type (System/Custom/Forked badges using `VerdictBadge` pattern), Used In (run count), Actions.

- [ ] **Step 3:** Row click navigates to evaluator detail (same page with `:id` param, or a state-based drilldown).

- [ ] **Step 4:** Page header has "Import CSV" + "New Evaluator" buttons. Wire "New Evaluator" to open the create overlay (Task 4).

- [ ] **Step 5:** Use `EmptyState` when no evaluators exist.

- [ ] **Step 6:** Commit incrementally.

---

### Task 3: Build Evaluator detail drilldown

**Files:**
- Create: `src/features/insideSales/components/EvaluatorDetail.tsx`

- [ ] **Step 1:** Follows the call detail drilldown pattern: back button, page header with badges, metadata bar, tabs.

- [ ] **Step 2:** Build:
  - Back button "Back to Evaluators"
  - Header: name + type badge + action buttons (Fork & Edit for system, Edit for own, Export CSV)
  - Metadata bar: dimensions, total pts, pass, excellent, compliance gates, used in
  - Tabs (reuse `Tabs`): Scoring Criteria / Compliance & Thresholds

- [ ] **Step 3:** **Scoring Criteria tab:** Parse `output_schema` to render dimension cards. Each number field = one dimension card with name + point allocation. Check items come from the rubric structure stored in evaluator config.

- [ ] **Step 4:** **Compliance & Thresholds tab:** Boolean fields in `output_schema` = compliance gates. Thresholds from field thresholds config.

- [ ] **Step 5:** Wire fork button to `POST /api/evaluators/{id}/fork?appId=inside-sales`, then open edit overlay with forked data.

- [ ] **Step 6:** Commit.

---

### Task 4: Extend CreateEvaluatorOverlay for rubric builder

**Files:**
- Modify: `src/features/evals/components/CreateEvaluatorOverlay.tsx`

- [ ] **Step 1:** Read the existing `CreateEvaluatorOverlay.tsx`. It has name, prompt template (textarea), and output schema builder (field-by-field). For inside-sales, we need a **rubric builder mode** that replaces the raw output schema builder.

- [ ] **Step 2:** Add a rubric builder that activates when `appId === 'inside-sales'`:
  - Dimensions & Checks builder: repeatable dimension blocks (name + max points + trash), each with repeatable check rows (trash + name + points)
  - Compliance gates section: repeatable gate text inputs with trash icons
  - Pass/Excellent threshold inputs

- [ ] **Step 3:** On save, the rubric builder serializes to the standard evaluator format:
  - `prompt` → generated from dimension/check/gate descriptions (LLM judge instruction template)
  - `output_schema` → dimension number fields + compliance booleans + reasoning field
  - Variable `{{transcript}}` is auto-included in the prompt

- [ ] **Step 4:** This is the most complex UI work. Build incrementally:
  1. First: conditional rendering (rubric builder vs standard schema builder) based on appId
  2. Then: dimension add/remove/edit
  3. Then: check items within dimensions
  4. Then: compliance gates
  5. Then: prompt auto-generation from rubric structure
  6. Then: thresholds

- [ ] **Step 5:** Test: create a new evaluator, verify it saves correctly, verify it shows in the table.

- [ ] **Step 6:** Commit after each working increment.

---

### Task 5: CSV import

**Files:**
- Create: `src/features/insideSales/components/EvaluatorCSVImport.tsx`

- [ ] **Step 1:** Build a simple modal (reuse `Modal` component) that:
  - Accepts a CSV file upload
  - Parses columns: `dimension`, `check`, `points`, `gate` (optional)
  - Previews parsed structure
  - On confirm, creates an evaluator via `POST /api/evaluators` with the parsed rubric

- [ ] **Step 2:** CSV format:
```csv
dimension,check,points
Call Opening & Permission,Clear self-introduction and company name,3
Call Opening & Permission,Reference to lead context,2
Call Opening & Permission,Asked permission or checked availability,3
...
[COMPLIANCE]
gate
No medical misinformation
No advice to stop prescribed medicines
```

- [ ] **Step 3:** Wire into the "Import CSV" button on the Evaluators page.

- [ ] **Step 4:** Commit.

---

### Task 6: Verify and merge

- [ ] **Step 1:** Full checks:
```bash
npx tsc -b && npm run lint && npm run build
```

- [ ] **Step 2:** Smoke test:
  - Navigate to Evaluators page — GoodFlip QA shows in table
  - Click into detail — dimensions and compliance render correctly
  - Fork the system evaluator — edit overlay opens pre-populated
  - Create a new evaluator from scratch via rubric builder
  - Import from CSV

- [ ] **Step 3:** Merge:
```bash
git checkout main && git merge feat/phase-3-evaluators
```
