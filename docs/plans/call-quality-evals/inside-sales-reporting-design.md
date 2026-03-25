# Inside Sales Reporting — Design Spec

**Date:** 2026-03-25
**Status:** Draft
**App ID:** `inside-sales`

## Overview

Reporting layer for inside sales call evaluations. Lives at RunDetail → Report tab (same placement as Kaira). Aggregates all call evals in a run, provides agent-level drill-down with heatmaps, and generates AI coaching commentary. Completely separate lens from Kaira — focused on human agent QA performance, behavioral signals, and sales outcomes.

## Architecture

**Pipeline:** Backend aggregates → LLM narrates → cache together → frontend renders

Reuses existing infrastructure:
- `EvaluationAnalytics` cache table (scope=`single_run`, app_id=`inside-sales`)
- `/api/reports/{run_id}` endpoint — branching in `handle_generate_report` (job_worker.py) based on `app_id`
- LLM provider abstraction (`llm_base.py`) for narrative generation
- User's configured LLM settings (provider/model at scope `(tenant_id, user_id, app_id="")` — same global settings pattern as Kaira)
- `ReportTab` shell component (generation trigger, loading, refresh, PDF export)

New code:
- `InsideSalesReportService` — parallel to `ReportService`, owns its own `generate()` method and `InsideSalesReportPayload` schema. Does NOT share return type with Kaira's `ReportPayload`.
- `InsideSalesAggregator` — computes aggregates from `ThreadEvaluation` rows
- `InsideSalesNarrator` — generates coaching commentary from aggregates
- `InsideSalesReportView` — frontend component rendering the report sections
- `lsq_agents` table — stable agent identity

### Service Separation (B1/B2 from review)

The existing `ReportService` returns `ReportPayload` (health_score, distributions, friction, exemplars) — a completely different shape from inside sales. Rather than polluting `ReportService` with conditionals:

- New `InsideSalesReportService` with its own `generate()` → `InsideSalesReportPayload`
- New `InsideSalesReportPayload` Pydantic schema in `backend/app/services/reports/inside_sales_schemas.py`
- `handle_generate_report` in `job_worker.py` branches on `eval_run.app_id` to pick the right service class
- Cache reads in `InsideSalesReportService._load_cache()` deserialize with `InsideSalesReportPayload.model_validate()`, not `ReportPayload`
- Both services write to the same `EvaluationAnalytics` table (JSONB column accepts any shape), but each validates with its own schema on read

## 1. Data Model

### New Table: `lsq_agents`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| tenant_id | UUID | FK → tenants (manual column, NOT via TenantUserMixin — agents are shared across platform users within a tenant) |
| lsq_user_id | String | Stable LSQ identifier, unique per tenant |
| name | String | Display name (latest from LSQ, updated on every fetch) |
| email | String | Nullable |
| created_at | Timestamp | |
| updated_at | Timestamp | Auto-update on name change |

**Unique constraint:** `(tenant_id, lsq_user_id)`

**Note on mixins:** Do NOT use `TenantUserMixin` — `lsq_agents` represents external sales agents, not platform users. Use a manual `tenant_id` FK column only. All queries filter by `tenant_id` from `AuthContext` per CLAUDE.md invariant.

**Upsert behavior:** On every LSQ data fetch, upsert by `(tenant_id, lsq_user_id)`. If exists, update `name` and `updated_at`. Eliminates string inconsistency for agent grouping.

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
    "agent_id": "uuid (FK → lsq_agents)",
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

### Result Nesting (B3 from review)

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
        "behavioral_flags": { ... },
        "outcome_flags": { ... },
        "compliance_no_misinformation": true,
        "reasoning": "..."
      }
    }
  ],
  "transcript": "...",
  "call_metadata": { ... }
}
```

- **QA rubric scores, behavioral flags, and outcome flags** all live inside `result["evaluations"][0]["output"]` (produced by the extended evaluator prompt)
- **Call metadata** lives at `result["call_metadata"]` (hydrated by the runner from LSQ, not LLM-extracted)
- The aggregator reads from `result["evaluations"][N]["output"]` for all scored/flag fields
- The runner resolves `agent_id` (UUID FK → `lsq_agents`) at eval time and stores it in `call_metadata.agent_id`
- `agent_name` in `call_metadata` is denormalized at eval time for convenience, but the **aggregator joins from `lsq_agents` at report generation time** for the latest name (since names can change between evals)

## 2. Aggregation Layer

### `InsideSalesAggregator`

**Location:** `backend/app/services/reports/inside_sales_aggregator.py`

**Input:** All `ThreadEvaluation` rows for a run + `lsq_agents` lookup

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
        # Per dimension: avg, min, max, distribution across verdict buckets
        "call_opening": {
            "avg": float, "min": float, "max": float, "maxPossible": 10,
            "distribution": [int, int, int, int, int]  # 5 buckets
        },
        # ... all 10 dimensions
    },

    "complianceBreakdown": {
        "no_misinformation": { "passed": int, "failed": int, "total": int },
        "no_stop_medicines": { "passed": int, "failed": int, "total": int },
        "no_guarantees": { "passed": int, "failed": int, "total": int }
    },

    "flagStats": {
        # Behavioral — dual denominator: reach (relevant/total) + conversion (present/relevant)
        "escalation": { "relevant": int, "notRelevant": int, "present": int },
        "disagreement": { "relevant": int, "notRelevant": int, "present": int },
        "tension": {
            "relevant": int, "notRelevant": int,
            "bySeverity": { "low": int, "medium": int, "high": int }
        },
        # Outcomes — dual denominator: reach + conversion
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
                "call_opening": { "avg": float },
                # ... all 10
            },
            "compliance": { "passed": int, "failed": int },
            "flags": { /* same shape as flagStats */ },
            "verdictDistribution": { "strong": int, "good": int, "needsWork": int, "poor": int }
        }
    },

    # Note: heatmap is derived from agentSlices on the frontend (sort by avgQaScore desc,
    # read dimensions from each slice). No separate heatmap key needed — avoids data redundancy.
    # Dimension order and maxScores come from the evaluator schema (already known to the frontend).
}
```

**Key decisions:**
- `agentSlices` pre-computed — frontend filters, no math
- `flagStats` always carries both denominators
- Heatmap is top-level for direct rendering
- **Two distinct threshold systems (do not confuse):**
  - **Verdict thresholds** (overall score buckets): Strong ≥80, Good ≥65, Needs Work ≥50, Poor <50. These classify entire calls.
  - **Dimension color thresholds** (per-dimension coloring): Come from evaluator schema fields (`green_threshold`, `yellow_threshold`). These color individual cells in the heatmap and dimension bars.

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
- Uses existing LLM provider abstraction (`llm_base.py`)
- Uses user's configured LLM settings at scope `(tenant_id, user_id, app_id="")` — same global settings pattern as existing `ReportService`, no per-app LLM settings
- Non-fatal narrative: generation is synchronous within the job (same as Kaira's `ReportService._generate_narrative`), but wrapped in try/catch — if it fails, the report still returns with data sections intact and `narrative: null`. Frontend shows "AI summary unavailable" placeholder.
- `agentCoachingNotes` keyed by agent UUID — shown only when agent drill-down is active
- Prompt tuned for sales QA coaching, not bot evaluation

## 4. Report UI — Frontend Components

### Placement

`Inside Sales > Runs > RunID > Report tab` — identical to Kaira placement. Report tab triggers generation via existing `submitAndPollJob()` pattern.

### Section Layout (top to bottom)

**Section 1: Executive Summary**
- Stat cards: Avg QA Score, Compliance %, Verdict Distribution (mini bar chart)
- AI narrative block (loads async, placeholder while generating)
- Reuse: stat card patterns from existing report components

**Section 2: QA Dimension Breakdown**
- Horizontal bar chart, all 10 dimensions
- Bar color from evaluator schema thresholds (green/yellow/red)
- Shows `avg / maxPossible` per dimension
- New component: `DimensionBreakdownChart`

**Section 3: Agent Performance Heatmap**
- Table: agents (rows) × dimensions (columns)
- Cells color-coded by threshold (green/yellow/red)
- Additional columns: call count, avg score, compliance %
- Click agent row → filters all other sections to that agent
- Active filter shown as chip at top, click to clear
- When filtered: sections 1, 2, 4, 5 re-render with agent's slice data
- New component: `AgentHeatmapTable`

**Section 4: Behavioral Signals & Outcomes**
- Two sub-sections: Behavioral Flags, Outcome Flags
- Each flag shows: count, reach (relevant/total), conversion (occurred/relevant)
- "Not relevant" count shown in muted text
- Cross-sell shows three-tier: reach → attempted → accepted
- New component: `FlagStatsPanel`

**Section 5: Compliance**
- Per-gate pass rate bar + violation count
- Color: green ≥95%, yellow ≥85%, red <85%
- New component: `ComplianceGatesPanel` (existing `RuleComplianceTable` is structurally different — it renders `RuleComplianceMatrix` with rule_id/section/co_failures, whereas inside sales has 3 simple boolean gates)

**Section 6: AI Coaching Notes** (conditional)
- Only visible when an agent is selected in the heatmap
- Shows narrator's per-agent coaching paragraph
- Styled with left-border accent, distinct from executive summary
- Part of `AgentHeatmapTable` or sibling component

**Section 7: AI Recommendations**
- Priority-tagged list (P0/P1/P2)
- From narrator output
- Reuse: `Recommendations` component pattern from existing report

### Component Reuse Plan

| Need | Reuse | New |
|------|-------|-----|
| Report tab shell (generate, loading, refresh, PDF) | `ReportTab.tsx` | — |
| Stat cards | Existing pattern | — |
| Job polling | `submitAndPollJob()` | — |
| API client | `reportsApi.ts` | — |
| Dimension bar chart | — | `DimensionBreakdownChart` |
| Agent heatmap table | — | `AgentHeatmapTable` |
| Flag stats panel | — | `FlagStatsPanel` |
| Compliance gates | — | `ComplianceGatesPanel` |
| Recommendations | `Recommendations.tsx` pattern | — |
| AI narrative block | `ExecutiveSummary.tsx` pattern | — |

## 5. Backend Integration

### Report Generation Flow

1. Frontend calls `POST /api/reports/{run_id}` (or triggers job for large runs)
2. `handle_generate_report` in `job_worker.py` loads the `EvalRun` and checks `app_id`
3. If `inside-sales` → dispatches to `InsideSalesReportService.generate()`; otherwise → existing `ReportService.generate()`
4. `InsideSalesReportService` reads all `ThreadEvaluation` rows, delegates to `InsideSalesAggregator`
5. Aggregator parses `result["evaluations"][0]["output"]` for scores/flags, joins `lsq_agents` for stable agent identity
6. Computes full `InsideSalesReportPayload`
7. `InsideSalesNarrator` generates AI commentary (synchronous but non-fatal — try/catch)
8. Both cached in `EvaluationAnalytics` (scope=`single_run`, JSONB column)
9. Returns `InsideSalesReportPayload` to frontend

### Agent Table Integration

- `lsq_agents` upserted during LSQ data fetch (existing `lsq_client.py` flow)
- At eval time, `call_metadata.agent_id` resolved from `lsq_agents` by `(tenant_id, lsq_user_id)`
- Aggregator groups by `agent_id`, joins for display name

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

### New Files

| File | Purpose |
|------|---------|
| `backend/app/models/lsq_agent.py` | `LsqAgent` ORM model |
| `backend/app/schemas/lsq_agent.py` | Pydantic schemas |
| `backend/app/services/reports/inside_sales_report_service.py` | Report service (generate, cache, load) |
| `backend/app/services/reports/inside_sales_schemas.py` | `InsideSalesReportPayload`, `InsideSalesNarrativeOutput` Pydantic schemas |
| `backend/app/services/reports/inside_sales_aggregator.py` | Aggregation logic |
| `backend/app/services/reports/inside_sales_narrator.py` | AI narrative generation |
| `src/features/insideSales/components/report/InsideSalesReportView.tsx` | Report container |
| `src/features/insideSales/components/report/DimensionBreakdownChart.tsx` | Dimension bars |
| `src/features/insideSales/components/report/AgentHeatmapTable.tsx` | Heatmap + drill-down |
| `src/features/insideSales/components/report/FlagStatsPanel.tsx` | Behavioral + outcome flags |
| `src/types/insideSalesReport.ts` | TypeScript types for report payload |

### Modified Files

| File | Change |
|------|--------|
| `backend/app/services/seed_defaults.py` | Extend GoodFlip QA prompt + output schema with flags |
| `backend/app/services/evaluators/inside_sales_runner.py` | Resolve `agent_id` from `lsq_agents` and store in `call_metadata` |
| `backend/app/jobs/job_worker.py` | Branch `handle_generate_report` on `app_id` to pick `InsideSalesReportService` vs `ReportService` |
| `backend/app/services/lsq_client.py` | Upsert `lsq_agents` on data fetch |
| `backend/app/models/__init__.py` | Register `LsqAgent` model |
| `src/features/insideSales/pages/InsideSalesRunDetail.tsx` | Wire Report tab to `InsideSalesReportView` |
