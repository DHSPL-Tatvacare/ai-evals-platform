# Phase 5b: Inside Sales — Reporting Layer

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the inside sales report aggregation, AI narrative, and report UI — aggregating all call evals in a run with agent-level drill-down heatmaps and coaching commentary.

**Architecture:** Extract `BaseReportService` from existing `ReportService` for cache/loading plumbing. New `InsideSalesReportService` extends it with its own aggregator (dynamic dimension reading from evaluator schema), narrator (sales QA coaching), and payload schema. Generic shared UI components (`HeatmapTable`, `DimensionBreakdownChart`, `FlagStatsPanel`, `ComplianceGatesPanel`) in `src/components/report/`. App-specific orchestrator and agent heatmap wrapper in `src/features/insideSales/`.

**Tech Stack:** Python (SQLAlchemy 2.0, Pydantic CamelModel), TypeScript (React, Tailwind, cn()), existing LLM provider abstraction, existing report caching.

**Branch:** `feat/phase-5b-reporting`

**Depends on:** Phase 4 (eval runs with ThreadEvaluation rows must exist). Phase 5 Results tab (run detail page exists with tabs).

**Spec:** `docs/plans/call-quality-evals/inside-sales-reporting-design.md`

---

## Task Overview

| # | Task | Type | Files |
|---|------|------|-------|
| 1 | ExternalAgent model + migration | Backend | 2 new, 1 modify |
| 2 | Extend seed defaults with behavioral/outcome flags | Backend | 1 modify |
| 3 | Update runner to resolve agent_id | Backend | 2 modify |
| 4 | Flag aggregation utility | Backend | 2 new |
| 5 | InsideSalesReportPayload schemas | Backend | 1 new |
| 6 | BaseReportService extraction | Backend | 1 new, 1 modify |
| 7 | InsideSalesAggregator | Backend | 1 new, 1 test |
| 8 | InsideSalesNarrator | Backend | 2 new |
| 9 | InsideSalesReportService + job worker wiring | Backend | 1 new, 1 modify |
| 10 | Frontend types | Frontend | 1 new |
| 11 | Shared report components | Frontend | 4 new |
| 12 | InsideSalesReportView + AgentHeatmapTable | Frontend | 2 new |
| 13 | Wire Report tab in RunDetail | Frontend | 1 modify |
| 14 | Housekeeping: schemas, CLAUDE.md | Docs | 2 modify, 1 new |
| 15 | Verify end-to-end | Integration | — |

---

### Task 1: ExternalAgent Model + Migration

**Files:**
- Create: `backend/app/models/external_agent.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create ExternalAgent ORM model**

```python
# backend/app/models/external_agent.py
"""External agent identity from CRM systems (LSQ, Salesforce, etc.)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ExternalAgent(Base, TimestampMixin):
    __tablename__ = "external_agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(30), nullable=False)  # "lsq", "salesforce", etc.
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "external_id", name="uq_external_agent_identity"),
        Index("idx_external_agent_tenant_source", "tenant_id", "source"),
    )
```

- [ ] **Step 2: Register in models/__init__.py**

Add to `backend/app/models/__init__.py`:
```python
from app.models.external_agent import ExternalAgent
```
And add `"ExternalAgent"` to `__all__`.

- [ ] **Step 3: Generate and apply migration**

```bash
cd backend
PYTHONPATH=. alembic revision --autogenerate -m "add external_agents table"
PYTHONPATH=. alembic upgrade head
```

Verify: table `external_agents` exists with `tenant_id`, `source`, `external_id`, `name`, `email`, `metadata`, `created_at`, `updated_at` columns and the unique constraint.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/external_agent.py backend/app/models/__init__.py backend/alembic/versions/
git commit -m "feat(reporting): add external_agents table for stable CRM agent identity"
```

---

### Task 2: Extend Seed Defaults with Behavioral/Outcome Flags

**Files:**
- Modify: `backend/app/services/seed_defaults.py`

- [ ] **Step 1: Add flag fields to GOODFLIP_QA_SCHEMA**

In `seed_defaults.py`, find `GOODFLIP_QA_SCHEMA` list. After the existing `reasoning` field, add:

```python
    # ── Behavioral flags ──
    {
        "key": "behavioral_flags",
        "type": "object",
        "label": "Behavioral Flags",
        "role": "flags",
        "hidden": True,
        "description": "Escalation, disagreement, and tension detection. Use 'not_relevant' if the signal does not apply to this call.",
    },
    # ── Outcome flags ──
    {
        "key": "outcome_flags",
        "type": "object",
        "label": "Outcome Flags",
        "role": "flags",
        "hidden": True,
        "description": "Meeting setup, purchase, callback, cross-sell outcomes. Use 'not_relevant' if the outcome was not applicable.",
    },
```

- [ ] **Step 2: Extend the evaluator prompt**

In `seed_defaults.py`, find the GoodFlip evaluator prompt string inside `INSIDE_SALES_EVALUATORS`. Append before the closing output instructions:

```
## BEHAVIORAL FLAGS

In addition to the scored dimensions above, extract the following behavioral signals from the call. For each flag, output one of: true, false, or "not_relevant" (if the behavior/situation did not arise in this call).

behavioral_flags:
  escalation:
    present: true | false | "not_relevant"
    evidence: "<quote or brief explanation>"
  disagreement:
    present: true | false | "not_relevant"
    evidence: "<quote or brief explanation>"
  tension_moments:
    moments: [{"quote": "<exact quote>", "severity": "low|medium|high"}] OR "not_relevant"

## OUTCOME FLAGS

Extract call outcomes. Use "not_relevant" if the outcome category was not applicable to this call (e.g., call was too short, wrong call type, no opportunity arose).

outcome_flags:
  meeting_setup:
    occurred: true | false | "not_relevant"
    evidence: "<quote or brief explanation>"
  purchase_made:
    occurred: true | false | "not_relevant"
    evidence: "<quote or brief explanation>"
  callback_scheduled:
    occurred: true | false | "not_relevant"
    evidence: "<quote or brief explanation>"
  cross_sell:
    attempted: true | false | "not_relevant"
    accepted: true | false | null
    products_mentioned: ["<product names>"]
    evidence: "<quote or brief explanation>"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/seed_defaults.py
git commit -m "feat(reporting): extend GoodFlip QA schema with behavioral and outcome flags"
```

---

### Task 3: Update Runner to Resolve agent_id

**Files:**
- Modify: `backend/app/services/evaluators/inside_sales_runner.py`
- Modify: `backend/app/services/lsq_client.py`

- [ ] **Step 1: Add agent upsert helper to lsq_client.py**

Add to `lsq_client.py`:

```python
async def upsert_external_agent(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    lsq_user_id: str,
    name: str,
    email: str | None = None,
) -> uuid.UUID:
    """Upsert an LSQ agent into external_agents. Returns the agent UUID."""
    from app.models.external_agent import ExternalAgent

    result = await db.execute(
        select(ExternalAgent).where(
            ExternalAgent.tenant_id == tenant_id,
            ExternalAgent.source == "lsq",
            ExternalAgent.external_id == lsq_user_id,
        )
    )
    agent = result.scalar_one_or_none()

    if agent:
        agent.name = name
        if email:
            agent.email = email
    else:
        agent = ExternalAgent(
            tenant_id=tenant_id,
            source="lsq",
            external_id=lsq_user_id,
            name=name,
            email=email,
        )
        db.add(agent)

    await db.flush()
    return agent.id
```

- [ ] **Step 2: Update runner call_metadata to include agent_id**

In `inside_sales_runner.py`, find the `ThreadEvaluation` creation block (~line 338-356). Before creating the `ThreadEvaluation`, resolve the agent:

```python
# Resolve stable agent identity
agent_name = call.get("agentName", "")
agent_lsq_id = call.get("agentId") or call.get("createdBy", "")
agent_id = None
if agent_lsq_id:
    agent_id = await upsert_external_agent(
        db, tenant_id=tenant_id, lsq_user_id=agent_lsq_id, name=agent_name,
    )

# Update call_metadata
"call_metadata": {
    "agent_id": str(agent_id) if agent_id else None,
    "agent": agent_name,
    "lead": call.get("_leadName", "") or call.get("prospectId", "")[:8],
    "prospect_id": call.get("prospectId", ""),
    "direction": call.get("direction"),
    "duration": call.get("durationSeconds"),
    "recording_url": recording_url,
},
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/lsq_client.py backend/app/services/evaluators/inside_sales_runner.py
git commit -m "feat(reporting): resolve agent_id from external_agents in runner"
```

---

### Task 4: Flag Aggregation Utility

**Files:**
- Create: `backend/app/services/reports/flag_utils.py`
- Create: `backend/tests/test_flag_utils.py`

- [ ] **Step 1: Write tests**

```python
# backend/tests/test_flag_utils.py
"""Tests for flag aggregation utilities."""

from app.services.reports.flag_utils import aggregate_flag, aggregate_outcome_flag


def test_aggregate_flag_counts_relevant_and_present():
    items = [
        {"present": True, "evidence": "heated exchange"},
        {"present": False, "evidence": "calm call"},
        {"present": "not_relevant"},
        {"present": True, "evidence": "raised voice"},
    ]
    result = aggregate_flag(items)
    assert result == {"relevant": 3, "notRelevant": 1, "present": 2}


def test_aggregate_flag_all_not_relevant():
    items = [{"present": "not_relevant"}, {"present": "not_relevant"}]
    result = aggregate_flag(items)
    assert result == {"relevant": 0, "notRelevant": 2, "present": 0}


def test_aggregate_flag_empty():
    assert aggregate_flag([]) == {"relevant": 0, "notRelevant": 0, "present": 0}


def test_aggregate_outcome_flag_dual_denominator():
    items = [
        {"attempted": True, "accepted": True, "evidence": "sold"},
        {"attempted": True, "accepted": False, "evidence": "declined"},
        {"attempted": False, "evidence": "no opportunity"},
        {"attempted": "not_relevant"},
    ]
    result = aggregate_outcome_flag(items, attempted_key="attempted", accepted_key="accepted")
    assert result == {"relevant": 3, "notRelevant": 1, "attempted": 2, "accepted": 1}


def test_aggregate_outcome_flag_simple_occurred():
    items = [
        {"occurred": True, "evidence": "meeting booked"},
        {"occurred": False, "evidence": "no meeting"},
        {"occurred": "not_relevant"},
    ]
    result = aggregate_outcome_flag(items, attempted_key="occurred")
    assert result == {"relevant": 2, "notRelevant": 1, "attempted": 1, "accepted": 0}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && PYTHONPATH=. pytest tests/test_flag_utils.py -v
```
Expected: ImportError

- [ ] **Step 3: Implement flag_utils.py**

```python
# backend/app/services/reports/flag_utils.py
"""Reusable flag aggregation with dual-denominator (reach + conversion) support.

Handles the 'not_relevant' pattern: flags where the signal didn't apply to a call
are excluded from denominators so agents aren't penalized for things that never arose.
"""

from __future__ import annotations


def aggregate_flag(
    items: list[dict],
    present_key: str = "present",
) -> dict:
    """Aggregate boolean flags with not_relevant support.

    Returns: { relevant, notRelevant, present }
    """
    relevant = 0
    not_relevant = 0
    present = 0

    for item in items:
        val = item.get(present_key)
        if val == "not_relevant":
            not_relevant += 1
        else:
            relevant += 1
            if val is True:
                present += 1

    return {"relevant": relevant, "notRelevant": not_relevant, "present": present}


def aggregate_outcome_flag(
    items: list[dict],
    attempted_key: str = "attempted",
    accepted_key: str | None = "accepted",
) -> dict:
    """Aggregate outcome flags with reach + conversion denominators.

    Returns: { relevant, notRelevant, attempted, accepted }
    """
    relevant = 0
    not_relevant = 0
    attempted = 0
    accepted = 0

    for item in items:
        val = item.get(attempted_key)
        if val == "not_relevant":
            not_relevant += 1
        else:
            relevant += 1
            if val is True:
                attempted += 1
                if accepted_key and item.get(accepted_key) is True:
                    accepted += 1

    return {
        "relevant": relevant,
        "notRelevant": not_relevant,
        "attempted": attempted,
        "accepted": accepted,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && PYTHONPATH=. pytest tests/test_flag_utils.py -v
```
Expected: All 5 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/reports/flag_utils.py backend/tests/test_flag_utils.py
git commit -m "feat(reporting): add reusable flag aggregation utility with dual denominators"
```

---

### Task 5: InsideSalesReportPayload Schemas

**Files:**
- Create: `backend/app/services/reports/inside_sales_schemas.py`

- [ ] **Step 1: Create Pydantic schemas**

```python
# backend/app/services/reports/inside_sales_schemas.py
"""Pydantic schemas for inside sales report payload.

Separate from schemas.py (Kaira) — completely different payload shape.
"""

from __future__ import annotations

from pydantic import Field

from app.schemas.base import CamelModel


class DimensionStats(CamelModel):
    label: str
    avg: float
    min: float
    max: float
    max_possible: float
    green_threshold: float
    yellow_threshold: float
    distribution: list[int] = Field(description="5 buckets")


class ComplianceGateStats(CamelModel):
    label: str
    passed: int
    failed: int
    total: int


class FlagStat(CamelModel):
    relevant: int
    not_relevant: int
    present: int = 0


class OutcomeFlagStat(CamelModel):
    relevant: int
    not_relevant: int
    attempted: int = 0
    accepted: int = 0


class TensionFlagStat(CamelModel):
    relevant: int
    not_relevant: int
    by_severity: dict[str, int] = Field(default_factory=dict)


class FlagStats(CamelModel):
    escalation: FlagStat
    disagreement: FlagStat
    tension: TensionFlagStat
    meeting_setup: OutcomeFlagStat
    purchase_made: OutcomeFlagStat
    callback_scheduled: OutcomeFlagStat
    cross_sell: OutcomeFlagStat


class VerdictDistribution(CamelModel):
    strong: int = 0
    good: int = 0
    needs_work: int = 0
    poor: int = 0


class RunSummary(CamelModel):
    total_calls: int
    evaluated_calls: int
    avg_qa_score: float
    verdict_distribution: VerdictDistribution
    compliance_pass_rate: float
    compliance_violation_count: int


class AgentDimensionAvg(CamelModel):
    avg: float


class AgentSlice(CamelModel):
    agent_name: str
    call_count: int
    avg_qa_score: float
    dimensions: dict[str, AgentDimensionAvg]
    compliance: dict[str, int]  # { "passed": N, "failed": N }
    flags: FlagStats
    verdict_distribution: VerdictDistribution


class DimensionInsight(CamelModel):
    dimension: str
    insight: str
    priority: str  # P0, P1, P2


class Recommendation(CamelModel):
    priority: str
    action: str


class InsideSalesNarrativeOutput(CamelModel):
    executive_summary: str
    dimension_insights: list[DimensionInsight] = Field(default_factory=list)
    agent_coaching_notes: dict[str, str] = Field(default_factory=dict)
    flag_patterns: str = ""
    compliance_alerts: list[str] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)


class InsideSalesReportMetadata(CamelModel):
    run_id: str
    run_name: str | None = None
    app_id: str
    eval_type: str
    created_at: str
    llm_provider: str | None = None
    llm_model: str | None = None
    narrative_model: str | None = None
    total_calls: int
    evaluated_calls: int
    duration_ms: float | None = None


class InsideSalesReportPayload(CamelModel):
    metadata: InsideSalesReportMetadata
    run_summary: RunSummary
    dimension_breakdown: dict[str, DimensionStats]
    compliance_breakdown: dict[str, ComplianceGateStats]
    flag_stats: FlagStats
    agent_slices: dict[str, AgentSlice]
    narrative: InsideSalesNarrativeOutput | None = None
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/reports/inside_sales_schemas.py
git commit -m "feat(reporting): add InsideSalesReportPayload Pydantic schemas"
```

---

### Task 6: BaseReportService Extraction

**Files:**
- Create: `backend/app/services/reports/base_report_service.py`
- Modify: `backend/app/services/reports/report_service.py`

- [ ] **Step 1: Create BaseReportService**

Extract reusable methods from `ReportService`:

```python
# backend/app/services/reports/base_report_service.py
"""Base report service with shared cache, data loading, and LLM setup."""

import logging
import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.eval_run import EvalRun, ThreadEvaluation, AdversarialEvaluation
from app.models.evaluation_analytics import EvaluationAnalytics
from app.services.evaluators.llm_base import LoggingLLMWrapper, create_llm_provider
from app.services.evaluators.runner_utils import save_api_log
from app.services.evaluators.settings_helper import get_llm_settings_from_db

logger = logging.getLogger(__name__)


class BaseReportService:
    """Shared plumbing for report generation services.

    Subclasses implement `generate()` with app-specific aggregation and narration.
    """

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    # --- Data loading ---

    async def _load_run(self, run_id: str) -> EvalRun:
        """Load EvalRun or raise ValueError (caught as 404 by route)."""
        run = await self.db.scalar(
            select(EvalRun).where(
                EvalRun.id == UUID(run_id),
                EvalRun.tenant_id == self.tenant_id,
                EvalRun.user_id == self.user_id,
            )
        )
        if not run:
            raise ValueError(f"Eval run not found: {run_id}")
        return run

    async def _load_threads(self, run_id: str) -> list[ThreadEvaluation]:
        """Load all ThreadEvaluation rows for a run."""
        result = await self.db.execute(
            select(ThreadEvaluation).where(ThreadEvaluation.run_id == UUID(run_id))
        )
        return list(result.scalars().all())

    async def _load_adversarial(self, run_id: str) -> list[AdversarialEvaluation]:
        """Load all AdversarialEvaluation rows for a run."""
        result = await self.db.execute(
            select(AdversarialEvaluation).where(
                AdversarialEvaluation.run_id == UUID(run_id)
            )
        )
        return list(result.scalars().all())

    # --- Cache ---

    async def _load_cache(self, run_id: str, app_id: str) -> dict | None:
        """Load cached report from evaluation_analytics table."""
        try:
            result = await self.db.execute(
                select(EvaluationAnalytics.analytics_data).where(
                    EvaluationAnalytics.scope == "single_run",
                    EvaluationAnalytics.run_id == UUID(run_id),
                    EvaluationAnalytics.app_id == app_id,
                    EvaluationAnalytics.tenant_id == self.tenant_id,
                )
            )
            row = result.scalar_one_or_none()
            return row if row else None
        except Exception as e:
            logger.warning("Failed to load cache for run %s: %s", run_id, e)
            return None

    async def _save_cache(self, run_id: str, app_id: str, data: dict) -> None:
        """Persist report data dict to evaluation_analytics table."""
        try:
            now = datetime.now(timezone.utc)

            result = await self.db.execute(
                select(EvaluationAnalytics).where(
                    EvaluationAnalytics.scope == "single_run",
                    EvaluationAnalytics.run_id == UUID(run_id),
                    EvaluationAnalytics.app_id == app_id,
                    EvaluationAnalytics.tenant_id == self.tenant_id,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.analytics_data = data
                existing.computed_at = now
            else:
                row = EvaluationAnalytics(
                    tenant_id=self.tenant_id,
                    app_id=app_id,
                    scope="single_run",
                    run_id=UUID(run_id),
                    analytics_data=data,
                    computed_at=now,
                )
                self.db.add(row)

            await self.db.commit()
        except Exception as e:
            logger.warning("Failed to cache report for run %s: %s", run_id, e)

    # --- LLM provider setup ---

    async def _create_llm_provider(
        self,
        run: EvalRun,
        thread_id: str,
        provider_override: str | None = None,
        model_override: str | None = None,
    ) -> tuple[LoggingLLMWrapper, str] | tuple[None, None]:
        """Create configured LLM provider with logging. Returns (llm, model_name) or (None, None)."""
        try:
            settings = await get_llm_settings_from_db(
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                auth_intent="managed_job",
                provider_override=provider_override or None,
            )

            effective_provider = provider_override or settings["provider"]
            effective_model = model_override or settings["selected_model"]

            if not effective_model:
                logger.warning("LLM setup skipped: no model specified")
                return None, None

            factory_kwargs = {}
            if effective_provider == "azure_openai":
                factory_kwargs["azure_endpoint"] = settings.get("azure_endpoint", "")
                factory_kwargs["api_version"] = settings.get("api_version", "")

            provider = create_llm_provider(
                provider=effective_provider,
                api_key=settings["api_key"],
                model_name=effective_model,
                service_account_path=settings.get("service_account_path", ""),
                **factory_kwargs,
            )

            llm = LoggingLLMWrapper(provider, log_callback=save_api_log)
            llm.set_context(run_id=str(run.id), thread_id=thread_id)
            return llm, effective_model
        except Exception as e:
            logger.warning("LLM setup failed: %s", e)
            return None, None
```

- [ ] **Step 2: Refactor existing ReportService to extend BaseReportService**

In `backend/app/services/reports/report_service.py`:

1. Change class declaration: `class ReportService(BaseReportService):`
2. Remove `__init__` (inherited)
3. Remove `_load_run`, `_load_threads`, `_load_adversarial`, `_load_cache`, `_save_cache` (inherited)
4. Update `_save_cache` call: `await self._save_cache(run_id, run.app_id, payload.model_dump())`
5. Update `_generate_narrative` and `_generate_custom_eval_narrative` to use `self._create_llm_provider()`
6. Add import: `from .base_report_service import BaseReportService`

Key changes in `generate()`:
```python
# Cache check — validate with ReportPayload
if not force_refresh:
    cached = await self._load_cache(run_id, run.app_id)
    if cached:
        try:
            return ReportPayload.model_validate(cached)
        except Exception:
            logger.warning("Report cache corrupted for run %s, regenerating", run_id)

# ... existing aggregation logic unchanged ...

# Cache — pass dict, not ReportPayload
await self._save_cache(run_id, run.app_id, payload.model_dump())
```

Key changes in `_generate_narrative()`:
```python
async def _generate_narrative(self, run, ...) -> tuple[NarrativeOutput | None, str | None]:
    llm, effective_model = await self._create_llm_provider(
        run, "report_narrative", llm_provider, llm_model,
    )
    if not llm:
        return None, None

    narrator = ReportNarrator(llm)
    result = await narrator.generate(...)
    return result, effective_model
```

- [ ] **Step 3: Verify existing Kaira reports still work**

```bash
cd backend && PYTHONPATH=. python -c "from app.services.reports.report_service import ReportService; print('Import OK')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/reports/base_report_service.py backend/app/services/reports/report_service.py
git commit -m "refactor(reporting): extract BaseReportService with shared cache, loading, and LLM setup"
```

---

### Task 7: InsideSalesAggregator

**Files:**
- Create: `backend/app/services/reports/inside_sales_aggregator.py`
- Create: `backend/tests/test_inside_sales_aggregator.py`

- [ ] **Step 1: Write tests**

```python
# backend/tests/test_inside_sales_aggregator.py
"""Tests for InsideSalesAggregator."""

from app.services.reports.inside_sales_aggregator import InsideSalesAggregator


def _make_eval_output(overall_score=75, call_opening=8, brand_positioning=10,
                       compliance_no_misinformation=True, compliance_no_guarantees=True,
                       behavioral_flags=None, outcome_flags=None):
    return {
        "overall_score": overall_score,
        "call_opening": call_opening,
        "brand_positioning": brand_positioning,
        "metabolism_explanation": 11,
        "metabolic_score_explanation": 7,
        "credibility_safety": 8,
        "transition_probing": 4,
        "probing_quality": 11,
        "intent_decision_mapping": 7,
        "program_mapping": 7,
        "closing_impression": 4,
        "compliance_no_misinformation": compliance_no_misinformation,
        "compliance_no_stop_medicines": True,
        "compliance_no_guarantees": compliance_no_guarantees,
        "reasoning": "test",
        "behavioral_flags": behavioral_flags or {
            "escalation": {"present": "not_relevant"},
            "disagreement": {"present": False, "evidence": "calm"},
            "tension_moments": {"moments": "not_relevant"},
        },
        "outcome_flags": outcome_flags or {
            "meeting_setup": {"occurred": True, "evidence": "booked"},
            "purchase_made": {"occurred": "not_relevant"},
            "callback_scheduled": {"occurred": False, "evidence": "no"},
            "cross_sell": {"attempted": "not_relevant"},
        },
    }


def _make_thread(thread_id, agent_id, output, agent_name="Agent"):
    """Simulates ThreadEvaluation-like dict for testing."""
    return {
        "thread_id": thread_id,
        "result": {
            "evaluations": [{"evaluator_id": "e1", "evaluator_name": "QA", "output": output}],
            "call_metadata": {"agent_id": agent_id, "agent": agent_name},
        },
        "success_status": True,
    }


def _schema():
    """Minimal evaluator output_schema for dimension discovery."""
    return [
        {"key": "overall_score", "type": "number", "main_metric": True, "max": 100, "green_threshold": 80, "yellow_threshold": 65},
        {"key": "call_opening", "type": "number", "max": 10, "green_threshold": 8, "yellow_threshold": 5, "label": "Call Opening"},
        {"key": "brand_positioning", "type": "number", "max": 15, "green_threshold": 12, "yellow_threshold": 8, "label": "Brand Positioning"},
        {"key": "compliance_no_misinformation", "type": "boolean", "label": "No Misinformation"},
        {"key": "compliance_no_stop_medicines", "type": "boolean", "label": "No Stop Medicines"},
        {"key": "compliance_no_guarantees", "type": "boolean", "label": "No Guarantees"},
    ]


AGENT_MAP = {"a1": "Priya", "a2": "Rajesh"}


def test_run_summary_basic():
    threads = [
        _make_thread("t1", "a1", _make_eval_output(overall_score=85)),
        _make_thread("t2", "a2", _make_eval_output(overall_score=65)),
    ]
    agg = InsideSalesAggregator(threads, _schema(), AGENT_MAP)
    result = agg.aggregate()

    assert result["runSummary"]["totalCalls"] == 2
    assert result["runSummary"]["evaluatedCalls"] == 2
    assert result["runSummary"]["avgQaScore"] == 75.0


def test_verdict_distribution():
    threads = [
        _make_thread("t1", "a1", _make_eval_output(overall_score=90)),  # strong
        _make_thread("t2", "a1", _make_eval_output(overall_score=70)),  # good
        _make_thread("t3", "a2", _make_eval_output(overall_score=55)),  # needsWork
        _make_thread("t4", "a2", _make_eval_output(overall_score=40)),  # poor
    ]
    agg = InsideSalesAggregator(threads, _schema(), AGENT_MAP)
    result = agg.aggregate()

    vd = result["runSummary"]["verdictDistribution"]
    assert vd == {"strong": 1, "good": 1, "needsWork": 1, "poor": 1}


def test_dimension_breakdown_dynamic_from_schema():
    threads = [_make_thread("t1", "a1", _make_eval_output(call_opening=8, brand_positioning=10))]
    agg = InsideSalesAggregator(threads, _schema(), AGENT_MAP)
    result = agg.aggregate()

    assert "call_opening" in result["dimensionBreakdown"]
    assert "brand_positioning" in result["dimensionBreakdown"]
    assert result["dimensionBreakdown"]["call_opening"]["maxPossible"] == 10
    assert result["dimensionBreakdown"]["call_opening"]["avg"] == 8.0


def test_compliance_breakdown():
    threads = [
        _make_thread("t1", "a1", _make_eval_output(compliance_no_misinformation=True, compliance_no_guarantees=False)),
        _make_thread("t2", "a2", _make_eval_output(compliance_no_misinformation=True, compliance_no_guarantees=True)),
    ]
    agg = InsideSalesAggregator(threads, _schema(), AGENT_MAP)
    result = agg.aggregate()

    assert result["complianceBreakdown"]["compliance_no_misinformation"]["passed"] == 2
    assert result["complianceBreakdown"]["compliance_no_guarantees"]["passed"] == 1
    assert result["complianceBreakdown"]["compliance_no_guarantees"]["failed"] == 1


def test_agent_slices():
    threads = [
        _make_thread("t1", "a1", _make_eval_output(overall_score=85), "Priya"),
        _make_thread("t2", "a1", _make_eval_output(overall_score=75), "Priya"),
        _make_thread("t3", "a2", _make_eval_output(overall_score=60), "Rajesh"),
    ]
    agg = InsideSalesAggregator(threads, _schema(), AGENT_MAP)
    result = agg.aggregate()

    assert "a1" in result["agentSlices"]
    assert result["agentSlices"]["a1"]["agentName"] == "Priya"
    assert result["agentSlices"]["a1"]["callCount"] == 2
    assert result["agentSlices"]["a1"]["avgQaScore"] == 80.0


def test_flag_stats_excludes_not_relevant():
    threads = [
        _make_thread("t1", "a1", _make_eval_output(outcome_flags={
            "meeting_setup": {"occurred": True, "evidence": "yes"},
            "purchase_made": {"occurred": "not_relevant"},
            "callback_scheduled": {"occurred": "not_relevant"},
            "cross_sell": {"attempted": "not_relevant"},
        })),
    ]
    agg = InsideSalesAggregator(threads, _schema(), AGENT_MAP)
    result = agg.aggregate()

    assert result["flagStats"]["meeting_setup"]["relevant"] == 1
    assert result["flagStats"]["meeting_setup"]["attempted"] == 1
    assert result["flagStats"]["purchase_made"]["notRelevant"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && PYTHONPATH=. pytest tests/test_inside_sales_aggregator.py -v
```
Expected: ImportError

- [ ] **Step 3: Implement InsideSalesAggregator**

```python
# backend/app/services/reports/inside_sales_aggregator.py
"""Aggregation engine for inside sales call evaluations.

Reads dimension keys dynamically from evaluator output_schema.
No hardcoded dimension names.
"""

from __future__ import annotations

import logging
from statistics import mean

from .flag_utils import aggregate_flag, aggregate_outcome_flag

logger = logging.getLogger(__name__)

# Verdict thresholds for overall score
VERDICT_THRESHOLDS = {"strong": 80, "good": 65, "needsWork": 50}


def _classify_verdict(score: float) -> str:
    if score >= VERDICT_THRESHOLDS["strong"]:
        return "strong"
    if score >= VERDICT_THRESHOLDS["good"]:
        return "good"
    if score >= VERDICT_THRESHOLDS["needsWork"]:
        return "needsWork"
    return "poor"


def _get_eval_output(thread: dict) -> dict | None:
    """Extract evaluator output from thread result."""
    result = thread.get("result", {})
    evals = result.get("evaluations", [])
    if evals:
        return evals[0].get("output", {})
    return None


def _get_call_metadata(thread: dict) -> dict:
    return thread.get("result", {}).get("call_metadata", {})


class InsideSalesAggregator:
    """Aggregates ThreadEvaluation data for inside sales reports.

    Args:
        threads: List of dicts with thread_id, result, success_status
        output_schema: Evaluator's output_schema (list of field defs)
        agent_names: Dict of agent_id → display name (from external_agents)
    """

    def __init__(
        self,
        threads: list[dict],
        output_schema: list[dict],
        agent_names: dict[str, str],
    ):
        self.threads = [t for t in threads if t.get("success_status")]
        self.output_schema = output_schema
        self.agent_names = agent_names

        # Discover dimensions and compliance gates from schema
        self.dimension_fields = []
        self.compliance_fields = []
        self.overall_score_key = "overall_score"

        for field in output_schema:
            key = field.get("key", "")
            ftype = field.get("type", "")
            if field.get("main_metric"):
                self.overall_score_key = key
            elif ftype == "number" and not field.get("hidden") and not field.get("role"):
                self.dimension_fields.append(field)
            elif ftype == "boolean" and key.startswith("compliance_"):
                self.compliance_fields.append(field)

    def aggregate(self) -> dict:
        outputs = []
        for t in self.threads:
            out = _get_eval_output(t)
            if out:
                outputs.append((t, out))

        return {
            "runSummary": self._run_summary(outputs),
            "dimensionBreakdown": self._dimension_breakdown(outputs),
            "complianceBreakdown": self._compliance_breakdown(outputs),
            "flagStats": self._flag_stats(outputs),
            "agentSlices": self._agent_slices(outputs),
        }

    def _run_summary(self, outputs: list[tuple]) -> dict:
        scores = [out.get(self.overall_score_key, 0) for _, out in outputs]
        avg = mean(scores) if scores else 0

        verdicts = {"strong": 0, "good": 0, "needsWork": 0, "poor": 0}
        for s in scores:
            verdicts[_classify_verdict(s)] += 1

        compliance_violations = 0
        for _, out in outputs:
            for cf in self.compliance_fields:
                if out.get(cf["key"]) is False:
                    compliance_violations += 1
                    break  # one violation per call is enough

        total = len(self.threads)
        evaluated = len(outputs)
        pass_count = evaluated - compliance_violations

        return {
            "totalCalls": total,
            "evaluatedCalls": evaluated,
            "avgQaScore": round(avg, 1),
            "verdictDistribution": verdicts,
            "compliancePassRate": round(pass_count / evaluated * 100, 1) if evaluated else 0,
            "complianceViolationCount": compliance_violations,
        }

    def _dimension_breakdown(self, outputs: list[tuple]) -> dict:
        breakdown = {}
        for field in self.dimension_fields:
            key = field["key"]
            values = [out.get(key, 0) for _, out in outputs if out.get(key) is not None]
            if not values:
                continue

            max_possible = field.get("max", 100)
            # 5 buckets evenly spaced
            bucket_size = max_possible / 5
            distribution = [0, 0, 0, 0, 0]
            for v in values:
                idx = min(int(v / bucket_size), 4) if bucket_size > 0 else 0
                distribution[idx] += 1

            breakdown[key] = {
                "label": field.get("label", key),
                "avg": round(mean(values), 1),
                "min": round(min(values), 1),
                "max": round(max(values), 1),
                "maxPossible": max_possible,
                "greenThreshold": field.get("green_threshold", max_possible * 0.8),
                "yellowThreshold": field.get("yellow_threshold", max_possible * 0.5),
                "distribution": distribution,
            }
        return breakdown

    def _compliance_breakdown(self, outputs: list[tuple]) -> dict:
        breakdown = {}
        for field in self.compliance_fields:
            key = field["key"]
            passed = sum(1 for _, out in outputs if out.get(key) is True)
            failed = sum(1 for _, out in outputs if out.get(key) is False)
            breakdown[key] = {
                "label": field.get("label", key),
                "passed": passed,
                "failed": failed,
                "total": passed + failed,
            }
        return breakdown

    def _flag_stats(self, outputs: list[tuple]) -> dict:
        bf_items = [out.get("behavioral_flags", {}) for _, out in outputs]
        of_items = [out.get("outcome_flags", {}) for _, out in outputs]

        # Tension needs special handling for severity
        tension_items = [bf.get("tension_moments", {}) for bf in bf_items]
        tension_relevant = 0
        tension_not_relevant = 0
        severity_counts = {"low": 0, "medium": 0, "high": 0}
        for item in tension_items:
            moments = item.get("moments", "not_relevant")
            if moments == "not_relevant":
                tension_not_relevant += 1
            else:
                tension_relevant += 1
                if isinstance(moments, list):
                    for m in moments:
                        sev = m.get("severity", "low")
                        if sev in severity_counts:
                            severity_counts[sev] += 1

        return {
            "escalation": aggregate_flag([bf.get("escalation", {}) for bf in bf_items]),
            "disagreement": aggregate_flag([bf.get("disagreement", {}) for bf in bf_items]),
            "tension": {
                "relevant": tension_relevant,
                "notRelevant": tension_not_relevant,
                "bySeverity": severity_counts,
            },
            "meeting_setup": aggregate_outcome_flag(
                [of.get("meeting_setup", {}) for of in of_items], attempted_key="occurred",
            ),
            "purchase_made": aggregate_outcome_flag(
                [of.get("purchase_made", {}) for of in of_items], attempted_key="occurred",
            ),
            "callback_scheduled": aggregate_outcome_flag(
                [of.get("callback_scheduled", {}) for of in of_items], attempted_key="occurred",
            ),
            "cross_sell": aggregate_outcome_flag(
                [of.get("cross_sell", {}) for of in of_items],
                attempted_key="attempted", accepted_key="accepted",
            ),
        }

    def _agent_slices(self, outputs: list[tuple]) -> dict:
        agent_groups: dict[str, list[tuple]] = {}
        for thread, out in outputs:
            meta = _get_call_metadata(thread)
            agent_id = meta.get("agent_id", "unknown")
            agent_groups.setdefault(agent_id, []).append((thread, out))

        slices = {}
        for agent_id, agent_outputs in agent_groups.items():
            scores = [out.get(self.overall_score_key, 0) for _, out in agent_outputs]
            verdicts = {"strong": 0, "good": 0, "needsWork": 0, "poor": 0}
            for s in scores:
                verdicts[_classify_verdict(s)] += 1

            dims = {}
            for field in self.dimension_fields:
                key = field["key"]
                values = [out.get(key, 0) for _, out in agent_outputs if out.get(key) is not None]
                dims[key] = {"avg": round(mean(values), 1) if values else 0}

            comp_passed = 0
            comp_failed = 0
            for _, out in agent_outputs:
                has_violation = False
                for cf in self.compliance_fields:
                    if out.get(cf["key"]) is False:
                        has_violation = True
                        break
                if has_violation:
                    comp_failed += 1
                else:
                    comp_passed += 1

            # Agent-level flag stats (reuse _flag_stats as static-compatible)
            agent_flags = self._flag_stats(agent_outputs)

            slices[agent_id] = {
                "agentName": self.agent_names.get(agent_id, agent_id),
                "callCount": len(agent_outputs),
                "avgQaScore": round(mean(scores), 1) if scores else 0,
                "dimensions": dims,
                "compliance": {"passed": comp_passed, "failed": comp_failed},
                "flags": agent_flags,
                "verdictDistribution": verdicts,
            }
        return slices
```

- [ ] **Step 4: Run tests**

```bash
cd backend && PYTHONPATH=. pytest tests/test_inside_sales_aggregator.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/reports/inside_sales_aggregator.py backend/tests/test_inside_sales_aggregator.py
git commit -m "feat(reporting): add InsideSalesAggregator with dynamic dimension reading"
```

---

### Task 8: InsideSalesNarrator

**Files:**
- Create: `backend/app/services/reports/inside_sales_narrator.py`
- Create: `backend/app/services/reports/prompts/inside_sales_narrative_prompt.py`

- [ ] **Step 1: Create the narrator prompt**

```python
# backend/app/services/reports/prompts/inside_sales_narrative_prompt.py
"""System prompt for inside sales report narrative generation."""

INSIDE_SALES_NARRATIVE_SYSTEM_PROMPT = """You are a sales QA analyst generating coaching insights from call evaluation data.

You will receive aggregated evaluation data for a batch of inside sales calls. Your job is to produce actionable coaching commentary.

Output MUST be valid JSON matching this schema:
{
  "executive_summary": "3-5 sentences: key findings, biggest strengths, biggest gaps",
  "dimension_insights": [
    {"dimension": "dimension_key", "insight": "what the data shows and why it matters", "priority": "P0|P1|P2"}
  ],
  "agent_coaching_notes": {
    "agent-uuid": "2-3 sentences: strengths, specific improvement areas, recommended actions"
  },
  "flag_patterns": "Cross-cutting observations about behavioral/outcome flags",
  "compliance_alerts": ["Specific compliance concerns requiring immediate attention"],
  "recommendations": [
    {"priority": "P0|P1|P2", "action": "Concrete, actionable recommendation"}
  ]
}

Guidelines:
- P0 = immediate action needed (compliance violations, severe performance gaps)
- P1 = coaching priority (systematic weakness across team or individual)
- P2 = optimization opportunity (good performance that could be great)
- Reference specific agents by name when giving coaching notes
- Connect flag patterns to dimension scores (e.g., "high escalation rate correlates with low probing quality")
- Be direct and specific — avoid generic advice like "improve communication skills"
- Compliance alerts are P0 by definition
"""
```

- [ ] **Step 2: Create the narrator class**

```python
# backend/app/services/reports/inside_sales_narrator.py
"""AI narrative generator for inside sales reports."""

import json
import logging

from app.services.evaluators.llm_base import BaseLLMProvider

from .inside_sales_schemas import InsideSalesNarrativeOutput
from .prompts.inside_sales_narrative_prompt import INSIDE_SALES_NARRATIVE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class InsideSalesNarrator:
    """Generates coaching commentary from aggregated inside sales data."""

    def __init__(self, llm: BaseLLMProvider):
        self.llm = llm

    async def generate(self, aggregate_data: dict) -> InsideSalesNarrativeOutput | None:
        """Generate narrative from aggregate payload. Returns None on failure."""
        try:
            user_prompt = (
                "Generate coaching insights for this inside sales call evaluation batch.\n\n"
                f"```json\n{json.dumps(aggregate_data, indent=2, default=str)}\n```"
            )

            response = await self.llm.generate_json(
                system_prompt=INSIDE_SALES_NARRATIVE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )

            if isinstance(response, str):
                response = json.loads(response)

            return InsideSalesNarrativeOutput.model_validate(response)
        except Exception as e:
            logger.warning("Inside sales narrative generation failed: %s", e)
            return None
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/reports/inside_sales_narrator.py backend/app/services/reports/prompts/inside_sales_narrative_prompt.py
git commit -m "feat(reporting): add InsideSalesNarrator with sales QA coaching prompt"
```

---

### Task 9: InsideSalesReportService + Job Worker Wiring

**Files:**
- Create: `backend/app/services/reports/inside_sales_report_service.py`
- Modify: `backend/app/services/job_worker.py`

- [ ] **Step 1: Create InsideSalesReportService**

```python
# backend/app/services/reports/inside_sales_report_service.py
"""Report service for inside sales evaluations.

Extends BaseReportService with inside-sales-specific aggregation and narration.
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import load_only

from app.models.eval_run import EvalRun
from app.models.evaluator import Evaluator
from app.models.external_agent import ExternalAgent

from .base_report_service import BaseReportService
from .inside_sales_aggregator import InsideSalesAggregator
from .inside_sales_narrator import InsideSalesNarrator
from .inside_sales_schemas import (
    InsideSalesReportMetadata,
    InsideSalesReportPayload,
)

logger = logging.getLogger(__name__)


class InsideSalesReportService(BaseReportService):
    """Inside sales report: QA aggregation + AI coaching narrative."""

    async def generate(
        self,
        run_id: str,
        force_refresh: bool = False,
        llm_provider: str | None = None,
        llm_model: str | None = None,
    ) -> InsideSalesReportPayload:
        run = await self._load_run(run_id)

        # Cache check
        if not force_refresh:
            cached = await self._load_cache(run_id, run.app_id)
            if cached:
                try:
                    return InsideSalesReportPayload.model_validate(cached)
                except Exception:
                    logger.warning("Inside sales report cache corrupted for run %s, regenerating", run_id)

        # Load data
        threads = await self._load_threads(run_id)
        thread_dicts = [
            {"thread_id": t.thread_id, "result": t.result, "success_status": t.success_status}
            for t in threads
        ]

        # Load evaluator schema for dynamic dimension discovery
        output_schema = await self._load_evaluator_schema(run)

        # Load agent names from external_agents
        agent_names = await self._load_agent_names(thread_dicts)

        # Aggregate
        aggregator = InsideSalesAggregator(thread_dicts, output_schema, agent_names)
        aggregate_data = aggregator.aggregate()

        # Metadata
        summary = run.summary or {}
        batch_meta = run.batch_metadata or {}
        metadata = InsideSalesReportMetadata(
            run_id=str(run.id),
            run_name=batch_meta.get("name"),
            app_id=run.app_id,
            eval_type=run.eval_type,
            created_at=run.created_at.isoformat() if run.created_at else "",
            llm_provider=run.llm_provider,
            llm_model=run.llm_model,
            total_calls=aggregate_data["runSummary"]["totalCalls"],
            evaluated_calls=aggregate_data["runSummary"]["evaluatedCalls"],
            duration_ms=run.duration_ms,
        )

        # AI Narrative (non-fatal)
        narrative = None
        narrative_model = None
        try:
            llm, model_name = await self._create_llm_provider(
                run, "inside_sales_narrative", llm_provider, llm_model,
            )
            if llm:
                narrator = InsideSalesNarrator(llm)
                narrative = await narrator.generate(aggregate_data)
                narrative_model = model_name
        except Exception as e:
            logger.warning("Inside sales narrative skipped: %s", e)

        metadata.narrative_model = narrative_model

        payload = InsideSalesReportPayload(
            metadata=metadata,
            run_summary=aggregate_data["runSummary"],
            dimension_breakdown=aggregate_data["dimensionBreakdown"],
            compliance_breakdown=aggregate_data["complianceBreakdown"],
            flag_stats=aggregate_data["flagStats"],
            agent_slices=aggregate_data["agentSlices"],
            narrative=narrative,
        )

        # Cache
        await self._save_cache(run_id, run.app_id, payload.model_dump())

        return payload

    async def _load_evaluator_schema(self, run: EvalRun) -> list[dict]:
        """Load evaluator output_schema for dimension discovery."""
        summary = run.summary or {}
        evaluator_id = None

        # Try from summary custom_evaluations
        custom_evals = summary.get("custom_evaluations", {})
        if custom_evals:
            evaluator_id = next(iter(custom_evals.keys()), None)

        # Try from run config
        if not evaluator_id:
            config = run.config or {}
            evaluator_id = config.get("evaluator_id")

        if not evaluator_id:
            logger.warning("No evaluator_id found for run %s, using empty schema", run.id)
            return []

        try:
            result = await self.db.execute(
                select(Evaluator).where(Evaluator.id == UUID(evaluator_id))
                .options(load_only(Evaluator.output_schema))
            )
            evaluator = result.scalar_one_or_none()
            return evaluator.output_schema or [] if evaluator else []
        except Exception as e:
            logger.warning("Failed to load evaluator schema: %s", e)
            return []

    async def _load_agent_names(self, threads: list[dict]) -> dict[str, str]:
        """Load agent display names from external_agents table."""
        agent_ids = set()
        for t in threads:
            meta = t.get("result", {}).get("call_metadata", {})
            aid = meta.get("agent_id")
            if aid:
                agent_ids.add(aid)

        if not agent_ids:
            return {}

        try:
            uuids = [UUID(aid) for aid in agent_ids]
            result = await self.db.execute(
                select(ExternalAgent).where(
                    ExternalAgent.id.in_(uuids),
                    ExternalAgent.tenant_id == self.tenant_id,
                )
                .options(load_only(ExternalAgent.id, ExternalAgent.name))
            )
            return {str(a.id): a.name for a in result.scalars().all()}
        except Exception as e:
            logger.warning("Failed to load agent names: %s", e)
            # Fallback to names from call_metadata
            names = {}
            for t in threads:
                meta = t.get("result", {}).get("call_metadata", {})
                aid = meta.get("agent_id")
                if aid and aid not in names:
                    names[aid] = meta.get("agent", aid)
            return names
```

- [ ] **Step 2: Update job_worker.py**

In `backend/app/services/job_worker.py`, find `handle_generate_report`. Add app_id branching:

```python
@register_job_handler("generate-report")
async def handle_generate_report(job_id, params: dict, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    import time as _time
    from app.database import async_session as _async_session
    from app.models.eval_run import EvalRun
    from sqlalchemy import select

    run_id = params.get("run_id")
    if not run_id:
        raise ValueError("run_id is required")

    start = _time.monotonic()

    await update_job_progress(job_id, 0, 2, "Aggregating evaluation data…", run_id=run_id)

    async with _async_session() as db:
        # Determine which service to use based on app_id
        from uuid import UUID as _UUID
        run = await db.scalar(
            select(EvalRun).where(EvalRun.id == _UUID(run_id), EvalRun.tenant_id == tenant_id)
        )
        if not run:
            raise ValueError(f"Eval run not found: {run_id}")

        if run.app_id == "inside-sales":
            from app.services.reports.inside_sales_report_service import InsideSalesReportService
            service = InsideSalesReportService(db, tenant_id=tenant_id, user_id=user_id)
        else:
            from app.services.reports.report_service import ReportService
            service = ReportService(db, tenant_id=tenant_id, user_id=user_id)

        await update_job_progress(job_id, 1, 2, "Generating AI narrative…", run_id=run_id)
        payload = await service.generate(
            run_id,
            force_refresh=params.get("refresh", False),
            llm_provider=params.get("provider"),
            llm_model=params.get("model"),
        )

    duration = round(_time.monotonic() - start, 2)

    # Return metadata — shape differs by service but we normalize here
    has_narrative = False
    health_grade = None
    if hasattr(payload, "narrative"):
        has_narrative = payload.narrative is not None
    if hasattr(payload, "health_score") and payload.health_score:
        health_grade = payload.health_score.grade

    return {
        "run_id": run_id,
        "duration_seconds": duration,
        "has_narrative": has_narrative,
        "health_grade": health_grade,
    }
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/reports/inside_sales_report_service.py backend/app/services/job_worker.py
git commit -m "feat(reporting): add InsideSalesReportService + wire job worker branching"
```

---

### Task 10: Frontend Types

**Files:**
- Create: `src/types/insideSalesReport.ts`

- [ ] **Step 1: Create TypeScript types matching backend schemas**

```typescript
// src/types/insideSalesReport.ts
// Types for inside sales report payload. Separate from reports.ts (Kaira).

export interface DimensionStats {
  label: string;
  avg: number;
  min: number;
  max: number;
  maxPossible: number;
  greenThreshold: number;
  yellowThreshold: number;
  distribution: number[];
}

export interface ComplianceGateStats {
  label: string;
  passed: number;
  failed: number;
  total: number;
}

export interface FlagStat {
  relevant: number;
  notRelevant: number;
  present: number;
}

export interface OutcomeFlagStat {
  relevant: number;
  notRelevant: number;
  attempted: number;
  accepted: number;
}

export interface TensionFlagStat {
  relevant: number;
  notRelevant: number;
  bySeverity: Record<string, number>;
}

export interface FlagStats {
  escalation: FlagStat;
  disagreement: FlagStat;
  tension: TensionFlagStat;
  meetingSetup: OutcomeFlagStat;
  purchaseMade: OutcomeFlagStat;
  callbackScheduled: OutcomeFlagStat;
  crossSell: OutcomeFlagStat;
}

export interface VerdictDistribution {
  strong: number;
  good: number;
  needsWork: number;
  poor: number;
}

export interface RunSummary {
  totalCalls: number;
  evaluatedCalls: number;
  avgQaScore: number;
  verdictDistribution: VerdictDistribution;
  compliancePassRate: number;
  complianceViolationCount: number;
}

export interface AgentSlice {
  agentName: string;
  callCount: number;
  avgQaScore: number;
  dimensions: Record<string, { avg: number }>;
  compliance: { passed: number; failed: number };
  flags: FlagStats;
  verdictDistribution: VerdictDistribution;
}

export interface DimensionInsight {
  dimension: string;
  insight: string;
  priority: string;
}

export interface Recommendation {
  priority: string;
  action: string;
}

export interface InsideSalesNarrative {
  executiveSummary: string;
  dimensionInsights: DimensionInsight[];
  agentCoachingNotes: Record<string, string>;
  flagPatterns: string;
  complianceAlerts: string[];
  recommendations: Recommendation[];
}

export interface InsideSalesReportMetadata {
  runId: string;
  runName: string | null;
  appId: string;
  evalType: string;
  createdAt: string;
  llmProvider: string | null;
  llmModel: string | null;
  narrativeModel: string | null;
  totalCalls: number;
  evaluatedCalls: number;
  durationMs: number | null;
}

export interface InsideSalesReportPayload {
  metadata: InsideSalesReportMetadata;
  runSummary: RunSummary;
  dimensionBreakdown: Record<string, DimensionStats>;
  complianceBreakdown: Record<string, ComplianceGateStats>;
  flagStats: FlagStats;
  agentSlices: Record<string, AgentSlice>;
  narrative: InsideSalesNarrative | null;
}
```

- [ ] **Step 2: Commit**

```bash
git add src/types/insideSalesReport.ts
git commit -m "feat(reporting): add InsideSalesReportPayload TypeScript types"
```

---

### Task 11: Shared Report Components

**Files:**
- Create: `src/components/report/DimensionBreakdownChart.tsx`
- Create: `src/components/report/HeatmapTable.tsx`
- Create: `src/components/report/FlagStatsPanel.tsx`
- Create: `src/components/report/ComplianceGatesPanel.tsx`

- [ ] **Step 1: Create src/components/report/ directory and DimensionBreakdownChart**

```typescript
// src/components/report/DimensionBreakdownChart.tsx
import { cn } from '@/utils/cn';

interface Dimension {
  key: string;
  label: string;
  avg: number;
  maxPossible: number;
  greenThreshold: number;
  yellowThreshold: number;
}

interface Props {
  dimensions: Dimension[];
  className?: string;
}

function getBarColor(avg: number, green: number, yellow: number): string {
  if (avg >= green) return 'var(--color-success, #22c55e)';
  if (avg >= yellow) return 'var(--color-warning, #eab308)';
  return 'var(--color-error, #ef4444)';
}

export function DimensionBreakdownChart({ dimensions, className }: Props) {
  return (
    <div className={cn('flex flex-col gap-2.5', className)}>
      {dimensions.map((d) => (
        <div key={d.key} className="flex items-center gap-3">
          <span className="text-sm w-48 flex-shrink-0 truncate" title={d.label}>
            {d.label}
          </span>
          <div className="flex-1 h-6 bg-[var(--bg-secondary)] rounded-md overflow-hidden">
            <div
              className="h-full rounded-md transition-all"
              style={{
                width: `${(d.avg / d.maxPossible) * 100}%`,
                backgroundColor: getBarColor(d.avg, d.greenThreshold, d.yellowThreshold),
              }}
            />
          </div>
          <span className="text-sm font-semibold w-14 text-right">
            {d.avg} / {d.maxPossible}
          </span>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Create HeatmapTable**

```typescript
// src/components/report/HeatmapTable.tsx
import { cn } from '@/utils/cn';

export interface HeatmapColumn {
  key: string;
  label: string;
  shortLabel?: string;
  max: number;
  greenThreshold: number;
  yellowThreshold: number;
}

export interface HeatmapRow {
  id: string;
  label: string;
  extraColumns?: { label: string; value: string | number; className?: string }[];
}

interface Props {
  rows: HeatmapRow[];
  columns: HeatmapColumn[];
  cells: Record<string, Record<string, number>>;
  selectedRowId?: string | null;
  onRowClick?: (rowId: string) => void;
  className?: string;
}

function cellColor(value: number, green: number, yellow: number): string {
  if (value >= green) return 'bg-green-500/20 text-green-500';
  if (value >= yellow) return 'bg-yellow-500/20 text-yellow-500';
  return 'bg-red-500/20 text-red-500';
}

export function HeatmapTable({ rows, columns, cells, selectedRowId, onRowClick, className }: Props) {
  return (
    <div className={cn('overflow-x-auto', className)}>
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="border-b-2 border-[var(--border)]">
            <th className="text-left p-2 w-28">Name</th>
            {rows[0]?.extraColumns?.map((ec, i) => (
              <th key={i} className="text-center p-2 w-12">{ec.label}</th>
            ))}
            {columns.map((col) => (
              <th key={col.key} className="text-center p-2" title={col.label}>
                <div className="text-[10px] leading-tight">{col.shortLabel || col.label}</div>
                <div className="text-[10px] text-[var(--text-secondary)]">/{col.max}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              className={cn(
                'border-b border-[var(--border)] cursor-pointer hover:bg-[var(--bg-secondary)] transition-colors',
                selectedRowId === row.id && 'bg-[var(--bg-secondary)] ring-1 ring-[var(--accent)]'
              )}
              onClick={() => onRowClick?.(row.id)}
            >
              <td className="p-2 font-semibold">{row.label}</td>
              {row.extraColumns?.map((ec, i) => (
                <td key={i} className={cn('text-center p-2', ec.className)}>{ec.value}</td>
              ))}
              {columns.map((col) => {
                const val = cells[row.id]?.[col.key] ?? 0;
                return (
                  <td key={col.key} className="text-center p-1.5">
                    <span className={cn('px-2 py-0.5 rounded font-semibold', cellColor(val, col.greenThreshold, col.yellowThreshold))}>
                      {val.toFixed(1)}
                    </span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 3: Create FlagStatsPanel**

```typescript
// src/components/report/FlagStatsPanel.tsx
import { cn } from '@/utils/cn';

interface BehavioralFlag {
  key: string;
  label: string;
  relevant: number;
  notRelevant: number;
  present: number;
  color?: string;
}

interface OutcomeFlag {
  key: string;
  label: string;
  relevant: number;
  notRelevant: number;
  attempted: number;
  accepted?: number;
  total: number;
}

interface Props {
  behavioralFlags?: BehavioralFlag[];
  outcomeFlags?: OutcomeFlag[];
  className?: string;
}

export function FlagStatsPanel({ behavioralFlags, outcomeFlags, className }: Props) {
  return (
    <div className={cn('space-y-6', className)}>
      {behavioralFlags && behavioralFlags.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold mb-3">Behavioral Flags</h4>
          <div className="grid grid-cols-3 gap-3">
            {behavioralFlags.map((f) => (
              <div key={f.key} className="bg-[var(--bg-primary)] p-3.5 rounded-lg border border-[var(--border)]">
                <div className="text-[11px] uppercase text-[var(--text-secondary)]">{f.label}</div>
                <div className="flex items-baseline gap-1.5 mt-1">
                  <span className={cn('text-2xl font-bold', f.color || 'text-[var(--color-error)]')}>{f.present}</span>
                  <span className="text-xs text-[var(--text-secondary)]">of {f.relevant} relevant</span>
                </div>
                <div className="text-[11px] text-[var(--text-secondary)] mt-1">
                  {f.notRelevant} calls — not relevant
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {outcomeFlags && outcomeFlags.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold mb-3">Outcome Flags</h4>
          <div className="grid grid-cols-4 gap-3">
            {outcomeFlags.map((f) => {
              const reachPct = f.total > 0 ? ((f.relevant / f.total) * 100).toFixed(0) : '0';
              const convPct = f.relevant > 0 ? ((f.attempted / f.relevant) * 100).toFixed(0) : '0';
              return (
                <div key={f.key} className="bg-[var(--bg-primary)] p-3.5 rounded-lg border border-[var(--border)]">
                  <div className="text-[11px] uppercase text-[var(--text-secondary)]">{f.label}</div>
                  <div className="text-2xl font-bold text-[var(--accent)] mt-1">{f.attempted}</div>
                  <div className="text-[11px] text-[var(--text-secondary)]">
                    Reach: {f.relevant}/{f.total} ({reachPct}%)
                  </div>
                  <div className="text-[11px] font-semibold text-[var(--accent)]">
                    Conv: {f.attempted}/{f.relevant} ({convPct}%)
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Create ComplianceGatesPanel**

```typescript
// src/components/report/ComplianceGatesPanel.tsx
import { cn } from '@/utils/cn';

interface Gate {
  key: string;
  label: string;
  passed: number;
  failed: number;
  total: number;
}

interface Props {
  gates: Gate[];
  className?: string;
}

function gateColor(rate: number): string {
  if (rate >= 95) return 'var(--color-success, #22c55e)';
  if (rate >= 85) return 'var(--color-warning, #eab308)';
  return 'var(--color-error, #ef4444)';
}

export function ComplianceGatesPanel({ gates, className }: Props) {
  return (
    <div className={cn('grid grid-cols-3 gap-3', className)}>
      {gates.map((g) => {
        const rate = g.total > 0 ? (g.passed / g.total) * 100 : 100;
        const color = gateColor(rate);
        return (
          <div key={g.key} className="bg-[var(--bg-primary)] p-3.5 rounded-lg border border-[var(--border)]">
            <div className="flex justify-between items-center">
              <span className="text-sm">{g.label}</span>
              <span className="text-sm font-bold" style={{ color }}>{rate.toFixed(0)}%</span>
            </div>
            <div className="h-1.5 bg-[var(--bg-secondary)] rounded-full mt-2 overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${rate}%`, backgroundColor: color }}
              />
            </div>
            <div className="text-[11px] text-[var(--text-secondary)] mt-1">
              {g.passed}/{g.total} passed · {g.failed} violations
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add src/components/report/
git commit -m "feat(reporting): add shared report components (DimensionBreakdown, Heatmap, Flags, Compliance)"
```

---

### Task 12: InsideSalesReportView + AgentHeatmapTable

**Files:**
- Create: `src/features/insideSales/components/report/AgentHeatmapTable.tsx`
- Create: `src/features/insideSales/components/report/InsideSalesReportView.tsx`

- [ ] **Step 1: Create AgentHeatmapTable**

```typescript
// src/features/insideSales/components/report/AgentHeatmapTable.tsx
import { useMemo } from 'react';
import { HeatmapTable, type HeatmapColumn, type HeatmapRow } from '@/components/report/HeatmapTable';
import type { AgentSlice, DimensionStats } from '@/types/insideSalesReport';
import { cn } from '@/utils/cn';

interface Props {
  agentSlices: Record<string, AgentSlice>;
  dimensionBreakdown: Record<string, DimensionStats>;
  selectedAgentId: string | null;
  onAgentSelect: (agentId: string | null) => void;
  coachingNote?: string | null;
  className?: string;
}

function scoreColor(score: number): string {
  if (score >= 80) return 'text-green-500';
  if (score >= 65) return 'text-yellow-500';
  return 'text-red-500';
}

export function AgentHeatmapTable({
  agentSlices, dimensionBreakdown, selectedAgentId, onAgentSelect, coachingNote, className,
}: Props) {
  const { rows, columns, cells } = useMemo(() => {
    const sorted = Object.entries(agentSlices).sort(([, a], [, b]) => b.avgQaScore - a.avgQaScore);

    const cols: HeatmapColumn[] = Object.entries(dimensionBreakdown).map(([key, dim]) => ({
      key,
      label: dim.label,
      shortLabel: dim.label.length > 10 ? dim.label.slice(0, 8) + '.' : dim.label,
      max: dim.maxPossible,
      greenThreshold: dim.greenThreshold,
      yellowThreshold: dim.yellowThreshold,
    }));

    const hRows: HeatmapRow[] = sorted.map(([id, slice]) => ({
      id,
      label: slice.agentName,
      extraColumns: [
        { label: 'Calls', value: slice.callCount },
        { label: 'Avg', value: slice.avgQaScore.toFixed(1), className: scoreColor(slice.avgQaScore) + ' font-bold' },
        {
          label: 'Compl.',
          value: slice.compliance.passed + slice.compliance.failed > 0
            ? `${((slice.compliance.passed / (slice.compliance.passed + slice.compliance.failed)) * 100).toFixed(0)}%`
            : '—',
        },
      ],
    }));

    const hCells: Record<string, Record<string, number>> = {};
    for (const [id, slice] of sorted) {
      hCells[id] = {};
      for (const col of cols) {
        hCells[id][col.key] = slice.dimensions[col.key]?.avg ?? 0;
      }
    }

    return { rows: hRows, columns: cols, cells: hCells };
  }, [agentSlices, dimensionBreakdown]);

  return (
    <div className={cn('space-y-4', className)}>
      {selectedAgentId && (
        <div className="flex items-center gap-2">
          <span className="bg-[var(--accent)] text-white px-3 py-1 rounded-full text-xs">
            Filtered: {agentSlices[selectedAgentId]?.agentName} ({agentSlices[selectedAgentId]?.callCount} calls)
          </span>
          <button
            className="text-xs text-[var(--text-secondary)] underline"
            onClick={() => onAgentSelect(null)}
          >
            Clear filter
          </button>
        </div>
      )}

      <HeatmapTable
        rows={rows}
        columns={columns}
        cells={cells}
        selectedRowId={selectedAgentId}
        onRowClick={(id) => onAgentSelect(selectedAgentId === id ? null : id)}
      />

      {selectedAgentId && coachingNote && (
        <div className="bg-[var(--bg-primary)] p-4 rounded-lg border-l-2 border-orange-500 text-sm leading-relaxed text-[var(--text-secondary)]">
          <div className="text-[11px] uppercase text-orange-500 mb-2 font-semibold">
            Agent Coaching Notes — {agentSlices[selectedAgentId]?.agentName}
          </div>
          {coachingNote}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create InsideSalesReportView**

```typescript
// src/features/insideSales/components/report/InsideSalesReportView.tsx
import { useMemo, useState } from 'react';
import { DimensionBreakdownChart } from '@/components/report/DimensionBreakdownChart';
import { FlagStatsPanel } from '@/components/report/FlagStatsPanel';
import { ComplianceGatesPanel } from '@/components/report/ComplianceGatesPanel';
import type { InsideSalesReportPayload } from '@/types/insideSalesReport';
import { cn } from '@/utils/cn';
import { AgentHeatmapTable } from './AgentHeatmapTable';

interface Props {
  report: InsideSalesReportPayload;
}

function verdictColor(score: number): string {
  if (score >= 80) return 'text-green-500';
  if (score >= 65) return 'text-yellow-500';
  return 'text-red-500';
}

export function InsideSalesReportView({ report }: Props) {
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);

  // When agent is selected, use their slice; otherwise use run-level data
  const activeSlice = selectedAgentId ? report.agentSlices[selectedAgentId] : null;

  const dimensions = useMemo(() => {
    return Object.entries(report.dimensionBreakdown).map(([key, dim]) => ({
      key,
      label: dim.label,
      avg: activeSlice ? (activeSlice.dimensions[key]?.avg ?? 0) : dim.avg,
      maxPossible: dim.maxPossible,
      greenThreshold: dim.greenThreshold,
      yellowThreshold: dim.yellowThreshold,
    }));
  }, [report.dimensionBreakdown, activeSlice]);

  const complianceGates = useMemo(() => {
    if (activeSlice) {
      // Approximate from agent slice compliance — per-gate not available at agent level
      // Show overall agent compliance
      return Object.entries(report.complianceBreakdown).map(([key, gate]) => ({
        key,
        label: gate.label,
        passed: gate.passed,
        failed: gate.failed,
        total: gate.total,
      }));
    }
    return Object.entries(report.complianceBreakdown).map(([key, gate]) => ({
      key, label: gate.label, passed: gate.passed, failed: gate.failed, total: gate.total,
    }));
  }, [report.complianceBreakdown, activeSlice]);

  const flagData = activeSlice?.flags ?? report.flagStats;
  const summary = activeSlice
    ? { avgQaScore: activeSlice.avgQaScore, callCount: activeSlice.callCount, verdictDistribution: activeSlice.verdictDistribution }
    : { avgQaScore: report.runSummary.avgQaScore, callCount: report.runSummary.evaluatedCalls, verdictDistribution: report.runSummary.verdictDistribution };

  const totalCalls = activeSlice ? activeSlice.callCount : report.runSummary.totalCalls;

  return (
    <div className="space-y-8">
      {/* Section 1: Executive Summary */}
      <section>
        <div className="grid grid-cols-3 gap-4 mb-4">
          <div className="bg-[var(--bg-primary)] p-4 rounded-lg border border-[var(--border)] text-center">
            <div className="text-[11px] uppercase text-[var(--text-secondary)]">Avg QA Score</div>
            <div className={cn('text-3xl font-bold', verdictColor(summary.avgQaScore))}>
              {summary.avgQaScore.toFixed(1)}
            </div>
            <div className="text-xs text-[var(--text-secondary)]">{summary.callCount} calls evaluated</div>
          </div>
          <div className="bg-[var(--bg-primary)] p-4 rounded-lg border border-[var(--border)] text-center">
            <div className="text-[11px] uppercase text-[var(--text-secondary)]">Compliance</div>
            <div className={cn('text-3xl font-bold', report.runSummary.compliancePassRate >= 90 ? 'text-green-500' : 'text-red-500')}>
              {report.runSummary.compliancePassRate.toFixed(0)}%
            </div>
            <div className="text-xs text-[var(--text-secondary)]">
              {report.runSummary.complianceViolationCount} violations
            </div>
          </div>
          <div className="bg-[var(--bg-primary)] p-4 rounded-lg border border-[var(--border)] text-center">
            <div className="text-[11px] uppercase text-[var(--text-secondary)]">Verdict</div>
            <div className="flex justify-center gap-1 mt-2">
              {(['strong', 'good', 'needsWork', 'poor'] as const).map((v) => {
                const colors = { strong: 'bg-green-500', good: 'bg-yellow-500', needsWork: 'bg-orange-500', poor: 'bg-red-500' };
                const count = summary.verdictDistribution[v];
                return (
                  <div key={v} className="text-center">
                    <div className={cn('w-6 rounded', colors[v])} style={{ height: Math.max(8, count * 2) }} />
                    <div className="text-[10px] mt-0.5">{count}</div>
                  </div>
                );
              })}
            </div>
            <div className="text-[10px] text-[var(--text-secondary)] mt-1">Strong · Good · Needs Work · Poor</div>
          </div>
        </div>

        {report.narrative?.executiveSummary && (
          <div className="bg-[var(--bg-primary)] p-4 rounded-lg border-l-2 border-[var(--accent)] text-sm leading-relaxed text-[var(--text-secondary)]">
            <div className="text-[11px] uppercase text-[var(--accent)] mb-2">AI Summary</div>
            {report.narrative.executiveSummary}
          </div>
        )}
      </section>

      {/* Section 2: Dimension Breakdown */}
      <section>
        <h3 className="text-sm font-semibold mb-3">QA Dimension Breakdown</h3>
        <DimensionBreakdownChart dimensions={dimensions} />
      </section>

      {/* Section 3: Agent Heatmap */}
      <section>
        <h3 className="text-sm font-semibold mb-3">Agent Performance</h3>
        <AgentHeatmapTable
          agentSlices={report.agentSlices}
          dimensionBreakdown={report.dimensionBreakdown}
          selectedAgentId={selectedAgentId}
          onAgentSelect={setSelectedAgentId}
          coachingNote={selectedAgentId ? report.narrative?.agentCoachingNotes[selectedAgentId] : null}
        />
      </section>

      {/* Section 4: Behavioral & Outcome Flags */}
      <section>
        <h3 className="text-sm font-semibold mb-3">Behavioral Signals & Outcomes</h3>
        <FlagStatsPanel
          behavioralFlags={[
            { key: 'escalation', label: 'Escalations', ...flagData.escalation, color: 'text-red-500' },
            { key: 'disagreement', label: 'Disagreements', ...flagData.disagreement, color: 'text-orange-500' },
            { key: 'tension', label: 'Tension Moments', relevant: flagData.tension.relevant, notRelevant: flagData.tension.notRelevant, present: Object.values(flagData.tension.bySeverity).reduce((a, b) => a + b, 0), color: 'text-orange-500' },
          ]}
          outcomeFlags={[
            { key: 'meetingSetup', label: 'Meeting Setup', ...flagData.meetingSetup, total: totalCalls },
            { key: 'purchaseMade', label: 'Purchase', ...flagData.purchaseMade, total: totalCalls },
            { key: 'callbackScheduled', label: 'Callback', ...flagData.callbackScheduled, total: totalCalls },
            { key: 'crossSell', label: 'Cross-sell', ...flagData.crossSell, total: totalCalls },
          ]}
        />
      </section>

      {/* Section 5: Compliance */}
      <section>
        <h3 className="text-sm font-semibold mb-3">Compliance</h3>
        <ComplianceGatesPanel gates={complianceGates} />
      </section>

      {/* Section 7: Recommendations */}
      {report.narrative?.recommendations && report.narrative.recommendations.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold mb-3">Recommendations</h3>
          <div className="space-y-3">
            {report.narrative.recommendations.map((rec, i) => {
              const colors: Record<string, string> = { P0: 'bg-red-500', P1: 'bg-orange-500', P2: 'bg-yellow-500' };
              return (
                <div key={i} className="flex gap-3 items-start">
                  <span className={cn('text-white px-2 py-0.5 rounded text-[11px] font-semibold flex-shrink-0', colors[rec.priority] || 'bg-gray-500')}>
                    {rec.priority}
                  </span>
                  <span className="text-sm">{rec.action}</span>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add src/features/insideSales/components/report/
git commit -m "feat(reporting): add InsideSalesReportView and AgentHeatmapTable"
```

---

### Task 13: Wire Report Tab in RunDetail

**Files:**
- Modify: `src/features/insideSales/pages/InsideSalesRunDetail.tsx`

- [ ] **Step 1: Replace placeholder with actual report tab**

In `InsideSalesRunDetail.tsx`, find the `reportTab` definition (~line 282-295). Replace the EmptyState with the actual report generation + view:

```typescript
// Add imports at top:
import { useState, useCallback } from 'react';
import { InsideSalesReportView } from '../components/report/InsideSalesReportView';
import type { InsideSalesReportPayload } from '@/types/insideSalesReport';
import { reportsApi } from '@/services/api/reportsApi';
import { submitAndPollJob } from '@/services/api/jobPolling';
import { notificationService } from '@/services/notifications';
import { Spinner } from '@/components/ui';
```

Replace the reportTab content:

```typescript
// Inside the component, add state:
const [report, setReport] = useState<InsideSalesReportPayload | null>(null);
const [reportStatus, setReportStatus] = useState<'idle' | 'loading' | 'generating' | 'ready' | 'error'>('idle');

const generateReport = useCallback(async (refresh = false) => {
  if (!runId) return;
  try {
    setReportStatus('generating');
    const result = await submitAndPollJob({
      jobType: 'generate-report',
      params: { run_id: runId, refresh },
      onProgress: () => {},
    });
    // Load the cached report
    const cached = await reportsApi.fetchReport(runId, { cacheOnly: true });
    setReport(cached as unknown as InsideSalesReportPayload);
    setReportStatus('ready');
  } catch (err) {
    setReportStatus('error');
    notificationService.error('Failed to generate report');
  }
}, [runId]);

// Try loading cached report on tab switch
const loadCachedReport = useCallback(async () => {
  if (!runId || report || reportStatus === 'generating') return;
  try {
    setReportStatus('loading');
    const cached = await reportsApi.fetchReport(runId, { cacheOnly: true });
    if (cached) {
      setReport(cached as unknown as InsideSalesReportPayload);
      setReportStatus('ready');
    } else {
      setReportStatus('idle');
    }
  } catch {
    setReportStatus('idle');
  }
}, [runId, report, reportStatus]);

// Replace reportTab:
// In the Tabs onChange handler (or useEffect), trigger report loading when report tab activates:
// Example: if the Tabs component uses onChange:
// <Tabs tabs={[resultsTab, reportTab]} onChange={(tabId) => { if (tabId === 'report') loadCachedReport(); }} />

const reportTab = {
  id: 'report',
  label: 'Report',
  content: (
    <div className="py-4">
      {reportStatus === 'ready' && report ? (
        <div className="space-y-4">
          <div className="flex justify-end">
            <button
              className="text-xs text-[var(--text-secondary)] underline"
              onClick={() => generateReport(true)}
            >
              Regenerate
            </button>
          </div>
          <InsideSalesReportView report={report} />
        </div>
      ) : reportStatus === 'generating' || reportStatus === 'loading' ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <Spinner />
          <p className="text-sm text-[var(--text-secondary)]">
            {reportStatus === 'generating' ? 'Generating report...' : 'Loading...'}
          </p>
        </div>
      ) : reportStatus === 'error' ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <p className="text-sm text-[var(--text-secondary)]">Failed to generate report.</p>
          <button className="text-sm text-[var(--accent)] underline" onClick={() => generateReport()}>
            Try again
          </button>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <p className="text-sm text-[var(--text-secondary)]">No report generated yet.</p>
          <button
            className="px-4 py-2 bg-[var(--accent)] text-white rounded-lg text-sm font-medium"
            onClick={() => generateReport()}
          >
            Generate Report
          </button>
        </div>
      )}
    </div>
  ),
};
```

- [ ] **Step 2: Verify typecheck**

```bash
npx tsc -b --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add src/features/insideSales/pages/InsideSalesRunDetail.tsx
git commit -m "feat(reporting): wire InsideSalesReportView into RunDetail Report tab"
```

---

### Task 14: Housekeeping — ExternalAgent Schemas + CLAUDE.md

**Files:**
- Create: `backend/app/schemas/external_agent.py`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Create ExternalAgent Pydantic schemas**

```python
# backend/app/schemas/external_agent.py
"""Request/response schemas for external agents."""

from app.schemas.base import CamelModel, CamelORMModel


class ExternalAgentResponse(CamelORMModel):
    id: str
    tenant_id: str
    source: str
    external_id: str
    name: str
    email: str | None = None
```

- [ ] **Step 2: Update CLAUDE.md eval_type registry**

In `CLAUDE.md`, find the `eval_type` list and add `call_quality`:

```
- EvalRun `eval_type` polymorphism must be preserved: `custom`, `full_evaluation`, `human`, `batch_thread`, `batch_adversarial`, `call_quality`.
```

Also add `external_agents` to the ORM tables count (19 → 20).

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/external_agent.py CLAUDE.md
git commit -m "docs: add ExternalAgent schemas and update CLAUDE.md with call_quality eval_type"
```

---

### Task 15: Verify End-to-End

- [ ] **Step 1: Verify backend imports**

```bash
cd backend && PYTHONPATH=. python -c "
from app.services.reports.base_report_service import BaseReportService
from app.services.reports.inside_sales_report_service import InsideSalesReportService
from app.services.reports.inside_sales_aggregator import InsideSalesAggregator
from app.services.reports.inside_sales_narrator import InsideSalesNarrator
from app.services.reports.flag_utils import aggregate_flag, aggregate_outcome_flag
from app.models.external_agent import ExternalAgent
print('All backend imports OK')
"
```

- [ ] **Step 2: Run all backend tests**

```bash
cd backend && PYTHONPATH=. pytest tests/ -v
```

- [ ] **Step 3: Verify frontend build**

```bash
npm run build
```

- [ ] **Step 4: Verify frontend lint**

```bash
npm run lint
```

- [ ] **Step 5: Final commit if any fixes needed**

```bash
git add <specific-files-that-changed>
git commit -m "fix(reporting): address build/lint issues from e2e verification"
```
