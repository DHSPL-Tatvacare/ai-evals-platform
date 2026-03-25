# Inside Sales Reporting — Design Spec

**Date:** 2026-03-25
**Status:** Draft
**App ID:** `inside-sales`

## Overview

Reporting layer for inside sales call evaluations. Lives at RunDetail → Report tab (same placement as Kaira). Aggregates all call evals in a run, provides agent-level drill-down with heatmaps, and generates AI coaching commentary. Completely separate lens from Kaira — focused on human agent QA performance, behavioral signals, and sales outcomes.

## Design Principles

1. **Extract, don't duplicate.** The existing `ReportService` has cache lifecycle, data loading, and LLM provider setup that any report service needs. Extract a `BaseReportService` so Inside Sales (and any future app) inherits plumbing and only implements app-specific aggregation + narration.
2. **Shared components in shared locations.** UI components that are generic (dimension bar charts, flag stats panels, heatmap tables, compliance gates) live in `src/components/report/`, not inside `src/features/insideSales/`. Only the report view orchestrator is app-specific.
3. **Generic agent identity.** The agent table is not LSQ-specific — it's an `external_agents` table with a `source` column, reusable if another CRM integration appears.
4. **Flag aggregation is a utility.** The dual-denominator (relevant/notRelevant/present) counting pattern is a reusable function, not embedded in the aggregator class.
5. **No hardcoded dimension names in aggregation logic.** The aggregator reads dimension keys and max scores from the evaluator's `output_schema` dynamically. Adding/removing dimensions = schema change only, no aggregator code change.

## Architecture

**Pipeline:** Backend aggregates → LLM narrates → cache together → frontend renders

### Reuses existing infrastructure:
- `EvaluationAnalytics` cache table (scope=`single_run`, app_id=`inside-sales`)
- `/api/reports/{run_id}` endpoint — branching in `handle_generate_report` (job_worker.py) based on `app_id`
- LLM provider abstraction (`llm_base.py`) for narrative generation
- User's configured LLM settings (provider/model at scope `(tenant_id, user_id, app_id="")` — same global settings pattern as Kaira)
- `ReportTab` shell component (generation trigger, loading, refresh, PDF export)
- `submitAndPollJob()` for async report generation
- `reportsApi.ts` for API calls

### New shared code (reusable by any app):
- `BaseReportService` — cache lifecycle, data loading, LLM provider setup
- `src/components/report/DimensionBreakdownChart` — bar chart for any scored dimensions
- `src/components/report/HeatmapTable` — generic rows × cols with threshold coloring
- `src/components/report/FlagStatsPanel` — dual-denominator flag display
- `src/components/report/ComplianceGatesPanel` — pass/fail gate display
- `aggregate_flags()` utility — counts relevant/notRelevant/present from flag arrays
- `external_agents` table — stable external identity for any CRM source

### New app-specific code:
- `InsideSalesReportService` extends `BaseReportService` — implements `_aggregate()` and `_narrate()`
- `InsideSalesAggregator` — computes inside-sales-specific aggregate payload
- `InsideSalesNarrator` — sales QA coaching prompt
- `InsideSalesReportView` — orchestrates shared components with inside-sales data shape
- `AgentHeatmapTable` — wraps generic `HeatmapTable` with agent click-to-filter behavior

### BaseReportService extraction

The existing `ReportService` methods split cleanly into reusable vs. app-specific:

| Method | Reusable (→ BaseReportService) | App-specific |
|--------|-------------------------------|-------------|
| `__init__(db, tenant_id, user_id)` | ✅ | |
| `_load_run(run_id)` | ✅ | |
| `_load_threads(run_id)` | ✅ | |
| `_load_adversarial(run_id)` | ✅ | |
| `_load_cache(run_id, app_id)` | ✅ | |
| `_save_cache(run_id, app_id, payload)` | ✅ (accepts `dict`, not `ReportPayload`) | |
| `_create_llm_provider(run, provider, model)` | ✅ (extract LLM setup boilerplate) | |
| `generate()` | | ✅ (each app implements its own pipeline) |
| `_generate_narrative()` | | ✅ (different narrator class + prompt) |
| `_build_metadata()` | | ✅ (different metadata shape) |
| Health score, exemplars, friction | | ✅ (Kaira-only concepts) |

**Refactor plan:**
1. Extract `BaseReportService` with the reusable methods
2. Existing `ReportService` extends `BaseReportService` (no behavior change for Kaira)
3. New `InsideSalesReportService` extends `BaseReportService`
4. `_save_cache` accepts `dict` (from `.model_dump()`) instead of `ReportPayload` — both services call `payload.model_dump()` before saving
5. `_load_cache` returns raw `dict` — each service validates with its own Pydantic schema
6. `_create_llm_provider` extracts the repeated settings-fetch + factory pattern used by both `_generate_narrative` and `_generate_custom_eval_narrative`

**Branching point:** `handle_generate_report` in `job_worker.py` loads the `EvalRun`, checks `app_id`, and dispatches to the right service class.

## 1. Data Model

### New Table: `external_agents`

Generic table for external agent identity from any CRM/system. Not LSQ-specific.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| tenant_id | UUID | FK → tenants (manual column, NOT via TenantUserMixin — agents are shared across platform users within a tenant) |
| source | String | CRM source identifier: `"lsq"`, `"salesforce"`, etc. |
| external_id | String | Stable identifier from the source system (e.g., LSQ user ID) |
| name | String | Display name (latest from source, updated on every fetch) |
| email | String | Nullable |
| metadata | JSONB | Nullable. Source-specific extra fields (team, role, etc.) |
| created_at | Timestamp | |
| updated_at | Timestamp | Auto-update on name/metadata change |

**Unique constraint:** `(tenant_id, source, external_id)`

**Note on mixins:** Do NOT use `TenantUserMixin` — external agents are not platform users. Use a manual `tenant_id` FK column only. All queries filter by `tenant_id` from `AuthContext` per CLAUDE.md invariant.

**Upsert behavior:** On every LSQ data fetch, upsert by `(tenant_id, source="lsq", external_id)`. If exists, update `name` and `updated_at`. Eliminates string inconsistency for agent grouping. Any future CRM integration follows the same pattern with a different `source` value.

### Eval Output: Extended Schema

The existing GoodFlip QA evaluator prompt produces 10 scored dimensions + 3 compliance gates + reasoning. The prompt is extended (or a second pass added) to also extract behavioral and outcome flags.

**QA Rubric (existing, unchanged):**
- `overall_score` (number, 0-100)
- `call_opening` (number, 0-10)
- `brand_positioning` (number, 0-15)
- `metabolism_explanation` (number, 0-15)
- `metabolic_score_explanation` (number, 0-10)
- `credibility_safety` (number, 0-10)
- `transition_probing` (number, 0-5)
- `probing_quality` (number, 0-15)
- `intent_decision_mapping` (number, 0-10)
- `program_mapping` (number, 0-10)
- `closing_impression` (number, 0-5)
- `compliance_no_misinformation` (boolean)
- `compliance_no_stop_medicines` (boolean)
- `compliance_no_guarantees` (boolean)
- `reasoning` (text)

**Behavioral Flags (new, extracted alongside):**
```json
{
  "behavioral_flags": {
    "escalation": { "present": true | false | "not_relevant", "evidence": "string" },
    "disagreement": { "present": true | false | "not_relevant", "evidence": "string" },
    "tension_moments": {
      "moments": [{ "quote": "string", "severity": "low|medium|high" }] | "not_relevant"
    }
  }
}
```

**Outcome Flags (new, extracted alongside):**
```json
{
  "outcome_flags": {
    "meeting_setup": { "occurred": true | false | "not_relevant", "evidence": "string" },
    "purchase_made": { "occurred": true | false | "not_relevant", "evidence": "string" },
    "callback_scheduled": { "occurred": true | false | "not_relevant", "evidence": "string" },
    "cross_sell": {
      "attempted": true | false | "not_relevant",
      "accepted": true | false | null,
      "products_mentioned": ["string"],
      "evidence": "string"
    }
  }
}
```

**"Not Relevant" semantics:** The LLM outputs `"not_relevant"` when a flag does not apply to the call (e.g., no cross-sell opportunity existed, call too short for probing). Aggregation excludes `not_relevant` from denominators.

**Call Metadata (hydrated from LSQ, not LLM-extracted):**
```json
{
  "call_metadata": {
    "agent_id": "uuid (FK → external_agents)",
    "agent_name": "string (denormalized for display)",
    "lead_name": "string",
    "city": "string",
    "call_direction": "Inbound | Outbound",
    "call_duration_seconds": 285,
    "event_type": "Welcome Call | Assessment | Follow-up | ...",
    "mql_score": 72,
    "age_group": "string",
    "condition": "string"
  }
}
```

### Result Nesting

The inside sales runner stores `ThreadEvaluation.result` in this structure:
```json
{
  "evaluations": [
    {
      "evaluator_id": "uuid",
      "evaluator_name": "GoodFlip Sales Call QA",
      "output": {
        "overall_score": 78,
        "call_opening": 8,
        "behavioral_flags": { "..." },
        "outcome_flags": { "..." },
        "compliance_no_misinformation": true,
        "reasoning": "..."
      }
    }
  ],
  "transcript": "...",
  "call_metadata": { "..." }
}
```

- **QA rubric scores, behavioral flags, and outcome flags** all live inside `result["evaluations"][0]["output"]` (produced by the extended evaluator prompt)
- **Call metadata** lives at `result["call_metadata"]` (hydrated by the runner from LSQ, not LLM-extracted)
- The aggregator reads from `result["evaluations"][N]["output"]` for all scored/flag fields
- The runner resolves `agent_id` (UUID FK → `external_agents`) at eval time and stores it in `call_metadata.agent_id`
- `agent_name` in `call_metadata` is denormalized at eval time for convenience, but the **aggregator joins from `external_agents` at report generation time** for the latest name (since names can change between evals)

## 2. Aggregation Layer

### Flag Aggregation Utility

**Location:** `backend/app/services/reports/flag_utils.py`

Reusable function for any app that has flags with `present | false | "not_relevant"` semantics:

```python
def aggregate_flags(
    items: list[dict],
    flag_path: str,       # e.g., "behavioral_flags.escalation"
    present_key: str = "present",  # key that holds True/False/"not_relevant"
) -> dict:
    """Returns { relevant: int, notRelevant: int, present: int }"""

def aggregate_outcome_flags(
    items: list[dict],
    flag_path: str,
    attempted_key: str = "attempted",
    accepted_key: str = "accepted",
) -> dict:
    """Returns { relevant: int, notRelevant: int, attempted: int, accepted: int }"""
```

Both functions skip items where the flag value is `"not_relevant"` in the denominator. Reusable by any future app that adopts the not-relevant pattern.

### `InsideSalesAggregator`

**Location:** `backend/app/services/reports/inside_sales_aggregator.py`

**Input:** All `ThreadEvaluation` rows for a run + evaluator `output_schema` (for dimension keys + thresholds) + `external_agents` lookup

**Dynamic dimension reading:** The aggregator does NOT hardcode dimension names. It reads the evaluator's `output_schema` to discover:
- Which fields are `type: "number"` → scored dimensions
- `max` value → maxPossible for that dimension
- `green_threshold`, `yellow_threshold` → color thresholds
- Which fields are `type: "boolean"` with `compliance_` prefix → compliance gates

This means adding/removing dimensions or compliance gates = evaluator schema change only. No aggregator code change.

**Output structure:**

```python
{
    "runSummary": {
        "totalCalls": int,
        "evaluatedCalls": int,
        "avgQaScore": float,
        "verdictDistribution": {
            "strong": int,    # 80-100
            "good": int,      # 65-79
            "needsWork": int,  # 50-64
            "poor": int       # < 50
        },
        "compliancePassRate": float,
        "complianceViolationCount": int
    },

    "dimensionBreakdown": {
        # Keys discovered from output_schema, not hardcoded
        "<dimension_key>": {
            "label": str,        # human-readable from schema
            "avg": float, "min": float, "max": float, "maxPossible": int,
            "greenThreshold": float, "yellowThreshold": float,
            "distribution": [int, int, int, int, int]  # 5 buckets
        },
        # ... all scored dimensions from schema
    },

    "complianceBreakdown": {
        # Keys discovered from output_schema (boolean fields with compliance_ prefix)
        "<gate_key>": { "label": str, "passed": int, "failed": int, "total": int },
        # ...
    },

    "flagStats": {
        # Computed by aggregate_flags() utility
        "escalation": { "relevant": int, "notRelevant": int, "present": int },
        "disagreement": { "relevant": int, "notRelevant": int, "present": int },
        "tension": {
            "relevant": int, "notRelevant": int,
            "bySeverity": { "low": int, "medium": int, "high": int }
        },
        "meeting_setup": { "relevant": int, "notRelevant": int, "occurred": int },
        "purchase_made": { "relevant": int, "notRelevant": int, "occurred": int },
        "callback_scheduled": { "relevant": int, "notRelevant": int, "occurred": int },
        "cross_sell": {
            "relevant": int, "notRelevant": int,
            "attempted": int, "accepted": int
        }
    },

    "agentSlices": {
        "<agent-uuid>": {
            "agentName": str,
            "callCount": int,
            "avgQaScore": float,
            "dimensions": {
                "<dimension_key>": { "avg": float },
                # ... all dimensions
            },
            "compliance": { "passed": int, "failed": int },
            "flags": { /* same shape as flagStats */ },
            "verdictDistribution": { "strong": int, "good": int, "needsWork": int, "poor": int }
        }
    },

    # Heatmap derived from agentSlices on frontend (sort by avgQaScore desc,
    # read dimensions from each slice). No separate key — avoids redundancy.
    # Dimension order and maxScores come from evaluator schema.
}
```

**Key decisions:**
- `agentSlices` pre-computed — frontend filters, no math
- `flagStats` always carries both denominators
- **Two distinct threshold systems (do not confuse):**
  - **Verdict thresholds** (overall score buckets): Strong ≥80, Good ≥65, Needs Work ≥50, Poor <50. These classify entire calls.
  - **Dimension color thresholds** (per-dimension coloring): Come from evaluator schema fields (`green_threshold`, `yellow_threshold`). Passed through in `dimensionBreakdown` for frontend to use.

## 3. AI Narrator

### `InsideSalesNarrator`

**Location:** `backend/app/services/reports/inside_sales_narrator.py`

**Input:** Full aggregate payload from `InsideSalesAggregator`

**Output:**
```python
{
    "executiveSummary": str,  # 3-5 sentences, key findings
    "dimensionInsights": [
        { "dimension": str, "insight": str, "priority": "P0|P1|P2" }
    ],
    "agentCoachingNotes": {
        "<agent-uuid>": str  # per-agent coaching paragraph
    },
    "flagPatterns": str,      # cross-cutting flag observations
    "complianceAlerts": [str], # specific compliance concerns
    "recommendations": [
        { "priority": "P0|P1|P2", "action": str }
    ]
}
```

**Behavior:**
- Uses `BaseReportService._create_llm_provider()` — no duplicated LLM setup boilerplate
- Uses user's configured LLM settings at scope `(tenant_id, user_id, app_id="")` — same global settings pattern as existing `ReportService`, no per-app LLM settings
- Non-fatal narrative: generation is synchronous within the job (same as Kaira's `ReportService._generate_narrative`), but wrapped in try/catch — if it fails, the report still returns with data sections intact and `narrative: null`. Frontend shows "AI summary unavailable" placeholder.
- `agentCoachingNotes` keyed by agent UUID — shown only when agent drill-down is active
- Prompt tuned for sales QA coaching, not bot evaluation

## 4. Report UI — Frontend Components

### Placement

`Inside Sales > Runs > RunID > Report tab` — identical to Kaira placement. Report tab triggers generation via existing `submitAndPollJob()` pattern.

### Shared Components (in `src/components/report/`)

These are generic, reusable by any app:

**`DimensionBreakdownChart`**
- Horizontal bar chart for any set of scored dimensions
- Props: `dimensions: { key, label, avg, maxPossible, greenThreshold, yellowThreshold }[]`
- Bar color computed from thresholds (green/yellow/red)
- No hardcoded dimension names — renders whatever is passed

**`HeatmapTable`**
- Generic rows × columns table with threshold-colored cells
- Props: `rows: { id, label, extraColumns }[]`, `columns: { key, label, max }[]`, `cells: Record<rowId, Record<colKey, number>>`, `thresholds: Record<colKey, { green, yellow }>`
- Supports row click callback for selection
- No knowledge of "agents" or "dimensions" — just renders data

**`FlagStatsPanel`**
- Displays flags with dual denominators (reach + conversion)
- Props: `flags: { key, label, relevant, notRelevant, present?, occurred?, attempted?, accepted? }[]`
- Renders count, reach %, conversion % with "not relevant" muted text
- Works for any flag shape — behavioral or outcome

**`ComplianceGatesPanel`**
- Pass/fail gate bars
- Props: `gates: { key, label, passed, failed, total }[]`
- Color thresholds: green ≥95%, yellow ≥85%, red <85%

### App-Specific Components (in `src/features/insideSales/components/report/`)

**`InsideSalesReportView`**
- Orchestrator: receives `InsideSalesReportPayload`, manages agent filter state, renders shared components with inside-sales data
- Handles agent selection state: when an agent is clicked, re-slices data from `agentSlices` and passes filtered data to all sections

**`AgentHeatmapTable`**
- Wraps `HeatmapTable` with agent-specific behavior:
  - Rows = agents (sorted by avgQaScore desc)
  - Extra columns: call count, avg score, compliance %
  - Click row → sets agent filter (managed by parent `InsideSalesReportView`)
  - Shows coaching notes panel below when agent is selected

### Component Location Summary

| Component | Location | Reusable? |
|-----------|----------|-----------|
| `DimensionBreakdownChart` | `src/components/report/` | ✅ Any app with scored dimensions |
| `HeatmapTable` | `src/components/report/` | ✅ Any rows × cols with thresholds |
| `FlagStatsPanel` | `src/components/report/` | ✅ Any app with behavioral/outcome flags |
| `ComplianceGatesPanel` | `src/components/report/` | ✅ Any app with pass/fail gates |
| `InsideSalesReportView` | `src/features/insideSales/components/report/` | ❌ Inside sales only |
| `AgentHeatmapTable` | `src/features/insideSales/components/report/` | ❌ Wraps HeatmapTable for agents |

### Section Layout (top to bottom)

**Section 1: Executive Summary**
- Stat cards: Avg QA Score, Compliance %, Verdict Distribution (mini bar chart)
- AI narrative block (placeholder while generating, "AI summary unavailable" on failure)
- Reuse: stat card patterns from existing report components

**Section 2: QA Dimension Breakdown**
- `DimensionBreakdownChart` — renders all dimensions from payload
- When agent filtered: shows that agent's dimension averages instead of run-wide

**Section 3: Agent Performance Heatmap**
- `AgentHeatmapTable` wrapping `HeatmapTable`
- Click agent row → filters all other sections to that agent's slice
- Active filter shown as chip at top, click to clear

**Section 4: Behavioral Signals & Outcomes**
- `FlagStatsPanel` — two instances (behavioral flags, outcome flags)
- When agent filtered: shows that agent's flag stats

**Section 5: Compliance**
- `ComplianceGatesPanel`
- When agent filtered: shows that agent's compliance breakdown

**Section 6: AI Coaching Notes** (conditional)
- Only visible when an agent is selected in the heatmap
- Shows narrator's per-agent coaching paragraph
- Styled with left-border accent, distinct from executive summary

**Section 7: AI Recommendations**
- Priority-tagged list (P0/P1/P2)
- From narrator output
- Reuse: `Recommendations` component pattern from existing report

### Existing Component Reuse

| Need | Reuse |
|------|-------|
| Report tab shell (generate, loading, refresh, PDF) | `ReportTab.tsx` |
| Stat cards | Existing pattern |
| Job polling | `submitAndPollJob()` |
| API client | `reportsApi.ts` |
| Recommendations list | `Recommendations.tsx` pattern |
| AI narrative block | `ExecutiveSummary.tsx` pattern |

## 5. Backend Integration

### Report Generation Flow

1. Frontend calls `POST /api/reports/{run_id}` (or triggers job for large runs)
2. `handle_generate_report` in `job_worker.py` loads the `EvalRun` and checks `app_id`
3. If `inside-sales` → dispatches to `InsideSalesReportService.generate()`; otherwise → existing `ReportService.generate()`
4. `InsideSalesReportService.generate()`:
   a. Checks cache via inherited `_load_cache()` → validates with `InsideSalesReportPayload`
   b. Loads threads via inherited `_load_threads()`
   c. Loads evaluator schema for dynamic dimension discovery
   d. Delegates to `InsideSalesAggregator` for computation
   e. Delegates to `InsideSalesNarrator` via inherited `_create_llm_provider()` (non-fatal)
   f. Caches via inherited `_save_cache()` with `payload.model_dump()`
   g. Returns `InsideSalesReportPayload`

### Agent Table Integration

- `external_agents` upserted during LSQ data fetch (existing `lsq_client.py` flow), with `source="lsq"`
- At eval time, `call_metadata.agent_id` resolved from `external_agents` by `(tenant_id, source="lsq", external_id)`
- Aggregator groups by `agent_id`, joins `external_agents` for latest display name

### Prompt Update

The GoodFlip QA evaluator prompt (`seed_defaults.py`) needs extension to also extract:
- `behavioral_flags` (escalation, disagreement, tension_moments)
- `outcome_flags` (meeting_setup, purchase_made, callback_scheduled, cross_sell)

Each flag supports `"not_relevant"` as a valid output when the signal doesn't apply to the call. The prompt instructs the LLM: "Output `not_relevant` if the behavior/outcome was not applicable to this call — e.g., no objection arose, call was too short for cross-sell opportunity."

The evaluator's `output_schema` in seed data must be updated to include the new fields.

## 6. Housekeeping Notes

- **`call_quality` eval_type:** The inside sales runner uses `eval_type="call_quality"` which is not yet documented in CLAUDE.md's `eval_type` list. Update CLAUDE.md to include it during implementation.
- **`src/types/insideSalesReport.ts`:** Separate from `src/types/reports.ts` — these are entirely different payload shapes and must not import from each other.

## 7. What Is NOT in Scope

- Efficiency metrics (talk-to-listen, dead air, pacing) — future phase
- Cross-run analytics for inside sales — future phase (reuse existing `CrossRunAggregator` pattern)
- LSQ metadata slicing in report (city, MQL, age_group filters) — future phase on top of cross-run
- PDF export customization — reuse existing PDF template
- New nav entries or dedicated analytics pages — report lives in existing Report tab

## 8. File Inventory

### New Files — Shared (reusable)

| File | Purpose |
|------|---------|
| `backend/app/models/external_agent.py` | `ExternalAgent` ORM model |
| `backend/app/schemas/external_agent.py` | Pydantic schemas |
| `backend/app/services/reports/base_report_service.py` | `BaseReportService` — cache, data loading, LLM setup |
| `backend/app/services/reports/flag_utils.py` | `aggregate_flags()`, `aggregate_outcome_flags()` utilities |
| `src/components/report/DimensionBreakdownChart.tsx` | Generic dimension bar chart |
| `src/components/report/HeatmapTable.tsx` | Generic rows × cols threshold table |
| `src/components/report/FlagStatsPanel.tsx` | Generic dual-denominator flag display |
| `src/components/report/ComplianceGatesPanel.tsx` | Generic pass/fail gate display |

### New Files — App-Specific

| File | Purpose |
|------|---------|
| `backend/app/services/reports/inside_sales_report_service.py` | `InsideSalesReportService` extends `BaseReportService` |
| `backend/app/services/reports/inside_sales_schemas.py` | `InsideSalesReportPayload`, `InsideSalesNarrativeOutput` |
| `backend/app/services/reports/inside_sales_aggregator.py` | Inside sales aggregation logic |
| `backend/app/services/reports/inside_sales_narrator.py` | Sales QA coaching narrative |
| `src/features/insideSales/components/report/InsideSalesReportView.tsx` | Report orchestrator |
| `src/features/insideSales/components/report/AgentHeatmapTable.tsx` | Agent heatmap wrapping HeatmapTable |
| `src/types/insideSalesReport.ts` | TypeScript types for payload |

### Modified Files

| File | Change |
|------|--------|
| `backend/app/services/reports/report_service.py` | Refactor to extend `BaseReportService` (no behavior change) |
| `backend/app/services/seed_defaults.py` | Extend GoodFlip QA prompt + output schema with flags |
| `backend/app/services/evaluators/inside_sales_runner.py` | Resolve `agent_id` from `external_agents` and store in `call_metadata` |
| `backend/app/jobs/job_worker.py` | Branch `handle_generate_report` on `app_id` |
| `backend/app/services/lsq_client.py` | Upsert `external_agents` (source="lsq") on data fetch |
| `backend/app/models/__init__.py` | Register `ExternalAgent` model |
| `src/features/insideSales/pages/InsideSalesRunDetail.tsx` | Wire Report tab to `InsideSalesReportView` |
