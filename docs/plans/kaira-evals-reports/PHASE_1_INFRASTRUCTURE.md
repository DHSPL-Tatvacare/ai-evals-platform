# Phase 1 — Infrastructure & Scaffolding

## Objective

Set up the backend service skeleton, Pydantic schemas (the `ReportPayload` contract), API endpoint, health score calculator, and frontend API client. No business logic yet — just the plumbing that everything builds on.

## Pre-flight

- Branch: `feat/report-phase-1-infra` from `main`
- Merge to `main` before starting Phase 2

---

## Step 1: Backend — Report Schemas (`backend/app/services/reports/schemas.py`)

Define the full `ReportPayload` contract as Pydantic models. This is the single source of truth for the backend→frontend interface. Use `CamelModel` base from `backend/app/schemas/base.py` for automatic camelCase serialization.

### Models to define:

```python
# All extend CamelModel for camelCase JSON output

class HealthScoreBreakdownItem(CamelModel):
    value: float        # raw 0–100
    weighted: float     # value × weight

class HealthScoreBreakdown(CamelModel):
    intent_accuracy: HealthScoreBreakdownItem
    correctness_rate: HealthScoreBreakdownItem
    efficiency_rate: HealthScoreBreakdownItem
    task_completion: HealthScoreBreakdownItem

class HealthScore(CamelModel):
    grade: str          # "A+", "B-", "F", etc.
    numeric: float      # 0–100
    breakdown: HealthScoreBreakdown

class VerdictDistributions(CamelModel):
    correctness: dict[str, int]
    efficiency: dict[str, int]
    adversarial: dict[str, int] | None  # null if no adversarial
    intent_histogram: IntentHistogram
    custom_evaluations: dict[str, CustomEvalSummary]

class IntentHistogram(CamelModel):
    buckets: list[str]   # ["0-20", "20-40", ...]
    counts: list[int]

class CustomEvalSummary(CamelModel):
    name: str
    type: str            # "numeric" | "text"
    average: float | None
    distribution: dict[str, int] | None

class RuleComplianceEntry(CamelModel):
    rule_id: str
    section: str
    passed: int
    failed: int
    rate: float
    severity: str        # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"

class CoFailure(CamelModel):
    rule_a: str
    rule_b: str
    co_occurrence_rate: float

class RuleComplianceMatrix(CamelModel):
    rules: list[RuleComplianceEntry]
    co_failures: list[CoFailure]

class FrictionPattern(CamelModel):
    description: str
    count: int
    example_thread_ids: list[str]

class FrictionAnalysis(CamelModel):
    total_friction_turns: int
    by_cause: dict[str, int]        # {"bot": n, "user": n}
    recovery_quality: dict[str, int] # {"GOOD": n, "PARTIAL": n, ...}
    avg_turns_by_verdict: dict[str, float]
    top_patterns: list[FrictionPattern]

class AdversarialCategoryResult(CamelModel):
    category: str
    passed: int
    total: int
    pass_rate: float

class AdversarialDifficultyResult(CamelModel):
    difficulty: str
    passed: int
    total: int

class AdversarialBreakdown(CamelModel):
    by_category: list[AdversarialCategoryResult]
    by_difficulty: list[AdversarialDifficultyResult]

class TranscriptMessage(CamelModel):
    role: str            # "user" | "assistant"
    content: str

class RuleViolation(CamelModel):
    rule_id: str
    evidence: str

class FrictionTurn(CamelModel):
    turn: int
    cause: str           # "bot" | "user"
    description: str

class ExemplarThread(CamelModel):
    thread_id: str
    composite_score: float
    intent_accuracy: float | None
    correctness_verdict: str | None
    efficiency_verdict: str | None
    task_completed: bool
    transcript: list[TranscriptMessage]
    rule_violations: list[RuleViolation]
    friction_turns: list[FrictionTurn]

class Exemplars(CamelModel):
    best: list[ExemplarThread]
    worst: list[ExemplarThread]

class ProductionPrompts(CamelModel):
    intent_classification: str | None
    meal_summary_spec: str | None

# --- AI Narrative (populated in Phase 3, nullable until then) ---

class TopIssue(CamelModel):
    rank: int
    area: str
    description: str
    affected_count: int
    example_thread_id: str | None

class ExemplarAnalysis(CamelModel):
    thread_id: str
    type: str            # "good" | "bad"
    what_happened: str
    why: str
    prompt_gap: str | None

class PromptGap(CamelModel):
    prompt_section: str
    eval_rule: str
    gap_type: str        # "UNDERSPEC" | "SILENT" | "LEAKAGE" | "CONFLICTING"
    description: str
    suggested_fix: str

class Recommendation(CamelModel):
    priority: str        # "P0" | "P1" | "P2"
    area: str
    action: str
    estimated_impact: str

class NarrativeOutput(CamelModel):
    executive_summary: str
    top_issues: list[TopIssue]
    exemplar_analysis: list[ExemplarAnalysis]
    prompt_gaps: list[PromptGap]
    recommendations: list[Recommendation]

# --- Top-level payload ---

class ReportMetadata(CamelModel):
    run_id: str
    run_name: str | None
    app_id: str
    eval_type: str
    created_at: str
    llm_provider: str | None
    llm_model: str | None
    total_threads: int
    completed_threads: int
    error_threads: int
    duration_ms: float | None
    data_path: str | None

class ReportPayload(CamelModel):
    metadata: ReportMetadata
    health_score: HealthScore
    distributions: VerdictDistributions
    rule_compliance: RuleComplianceMatrix
    friction: FrictionAnalysis
    adversarial: AdversarialBreakdown | None
    exemplars: Exemplars
    production_prompts: ProductionPrompts
    narrative: NarrativeOutput | None  # null until Phase 3 builds narrator
```

### Key decisions:
- Use `CamelModel` (already in codebase) — automatic camelCase serialization
- `narrative` is nullable — Phase 2 returns the report without AI narrative, Phase 3 populates it
- All numeric fields are raw (not pre-formatted) — frontend handles display formatting
- `production_prompts` are static strings, not structured — they're for show-and-tell only

---

## Step 2: Backend — Health Score Calculator (`backend/app/services/reports/health_score.py`)

Pure function, no DB access, no LLM calls. Takes summary dict, returns `HealthScore`.

```python
# Pseudocode

WEIGHTS = {
    "intent_accuracy": 0.25,
    "correctness_rate": 0.25,
    "efficiency_rate": 0.25,
    "task_completion": 0.25,
}

GRADE_THRESHOLDS = [
    (95, "A+"), (90, "A"), (85, "A-"),
    (80, "B+"), (75, "B"), (70, "B-"),
    (65, "C+"), (60, "C"), (55, "C-"),
    (50, "D+"), (45, "D"), (0, "F"),
]

def compute_health_score(
    avg_intent_accuracy: float | None,       # 0–1 from summary
    correctness_verdicts: dict[str, int],     # {"PASS": n, "SOFT FAIL": n, ...}
    efficiency_verdicts: dict[str, int],      # {"EFFICIENT": n, "ACCEPTABLE": n, ...}
    total_evaluated: int,
    success_count: int,                       # threads with task_completed=True
) -> HealthScore:
    """Compute weighted health score from summary metrics."""

    # Normalize to 0–100
    intent = (avg_intent_accuracy or 0) * 100
    correct = (correctness_verdicts.get("PASS", 0) / max(total_evaluated, 1)) * 100
    efficient = (
        (efficiency_verdicts.get("EFFICIENT", 0) + efficiency_verdicts.get("ACCEPTABLE", 0))
        / max(total_evaluated, 1)
    ) * 100
    task_comp = (success_count / max(total_evaluated, 1)) * 100

    numeric = (
        intent * WEIGHTS["intent_accuracy"]
        + correct * WEIGHTS["correctness_rate"]
        + efficient * WEIGHTS["efficiency_rate"]
        + task_comp * WEIGHTS["task_completion"]
    )

    grade = next(g for threshold, g in GRADE_THRESHOLDS if numeric >= threshold)

    return HealthScore(
        grade=grade,
        numeric=round(numeric, 1),
        breakdown=HealthScoreBreakdown(
            intent_accuracy=HealthScoreBreakdownItem(value=round(intent, 1), weighted=round(intent * 0.25, 1)),
            correctness_rate=HealthScoreBreakdownItem(value=round(correct, 1), weighted=round(correct * 0.25, 1)),
            efficiency_rate=HealthScoreBreakdownItem(value=round(efficient, 1), weighted=round(efficient * 0.25, 1)),
            task_completion=HealthScoreBreakdownItem(value=round(task_comp, 1), weighted=round(task_comp * 0.25, 1)),
        ),
    )
```

### Design notes:
- Pure function — easy to unit test
- Handles missing data gracefully (None intent → 0)
- Weights are constants at module level — easy to adjust later or make configurable
- Returns Pydantic model directly (no dicts)
- The function signature takes pre-extracted values, NOT raw DB models — keeps it decoupled from ORM

---

## Step 3: Backend — Service Skeleton (`backend/app/services/reports/`)

Create the directory and service orchestrator.

### `backend/app/services/reports/__init__.py`
```python
from .report_service import ReportService

__all__ = ["ReportService"]
```

### `backend/app/services/reports/report_service.py`
```python
"""Orchestrates report generation: aggregate → narrate → assemble."""

class ReportService:
    """
    Stateless service. Receives a DB session, loads data, computes everything.

    Usage:
        service = ReportService(db_session)
        payload = await service.generate(run_id)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate(self, run_id: str) -> ReportPayload:
        """
        Full report generation pipeline.

        1. Load EvalRun + ThreadEvaluations + AdversarialEvaluations
        2. Aggregate (Phase 2)
        3. Narrate via LLM (Phase 3 — returns None until implemented)
        4. Assemble ReportPayload
        """
        # Phase 1: Just load and return stub
        run = await self._load_run(run_id)
        threads = await self._load_threads(run_id)
        adversarial = await self._load_adversarial(run_id)

        # Phase 2 will replace this with real aggregation
        # Phase 3 will add narrative generation

        metadata = self._build_metadata(run, threads, adversarial)
        health_score = self._compute_health_score(run)

        return ReportPayload(
            metadata=metadata,
            health_score=health_score,
            distributions=VerdictDistributions(...),  # Phase 2
            rule_compliance=RuleComplianceMatrix(rules=[], co_failures=[]),  # Phase 2
            friction=FrictionAnalysis(...),  # Phase 2
            adversarial=None,  # Phase 2
            exemplars=Exemplars(best=[], worst=[]),  # Phase 2
            production_prompts=ProductionPrompts(
                intent_classification=None,
                meal_summary_spec=None,
            ),  # Phase 3
            narrative=None,  # Phase 3
        )

    async def _load_run(self, run_id: str) -> EvalRun:
        """Load EvalRun or raise 404."""
        ...

    async def _load_threads(self, run_id: str) -> list[ThreadEvaluation]:
        """Load all ThreadEvaluation rows for run."""
        ...

    async def _load_adversarial(self, run_id: str) -> list[AdversarialEvaluation]:
        """Load all AdversarialEvaluation rows for run."""
        ...

    def _build_metadata(self, run, threads, adversarial) -> ReportMetadata:
        """Extract metadata from run + counts."""
        ...

    def _compute_health_score(self, run) -> HealthScore:
        """Delegate to health_score module using run.summary."""
        ...
```

### Design:
- `ReportService` is stateless per-request (receives `db` in constructor)
- Follows same pattern as existing evaluator services
- Each phase fills in more of the `ReportPayload` — the stub returns valid but empty sections
- Private methods prefixed with `_` for internal data loading

---

## Step 4: Backend — API Route (`backend/app/routes/reports.py`)

```python
"""Report generation endpoint."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.reports import ReportService
from app.services.reports.schemas import ReportPayload

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/{run_id}", response_model=ReportPayload)
async def get_report(run_id: str, db: AsyncSession = Depends(get_db)):
    """
    Generate an evaluation report for a completed run.

    Returns the full ReportPayload with metrics, distributions,
    rule compliance, exemplars, and AI narrative.
    """
    service = ReportService(db)
    try:
        return await service.generate(run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

### Register in `backend/app/main.py`:
```python
from app.routes.reports import router as reports_router
# Add to existing router includes:
app.include_router(reports_router)
```

### Key decisions:
- **Separate router** (`/api/reports/`) not nested under `/api/eval-runs/` — reports are a distinct domain, and this supports future expansion (multi-run reports, scheduled reports, etc.)
- Single endpoint for now — `GET /api/reports/{run_id}`
- Returns the full payload in one response — no pagination needed (report data is bounded)
- 404 if run doesn't exist or isn't a batch_thread type

---

## Step 5: Frontend — TypeScript Types (`src/types/reports.ts`)

Mirror the Pydantic schemas as TypeScript interfaces. These MUST match the backend CamelModel output exactly.

```typescript
// src/types/reports.ts

export interface HealthScoreBreakdownItem {
  value: number;
  weighted: number;
}

export interface HealthScoreBreakdown {
  intentAccuracy: HealthScoreBreakdownItem;
  correctnessRate: HealthScoreBreakdownItem;
  efficiencyRate: HealthScoreBreakdownItem;
  taskCompletion: HealthScoreBreakdownItem;
}

export interface HealthScore {
  grade: string;
  numeric: number;
  breakdown: HealthScoreBreakdown;
}

export interface IntentHistogram {
  buckets: string[];
  counts: number[];
}

export interface CustomEvalSummary {
  name: string;
  type: 'numeric' | 'text';
  average: number | null;
  distribution: Record<string, number> | null;
}

export interface VerdictDistributions {
  correctness: Record<string, number>;
  efficiency: Record<string, number>;
  adversarial: Record<string, number> | null;
  intentHistogram: IntentHistogram;
  customEvaluations: Record<string, CustomEvalSummary>;
}

export interface RuleComplianceEntry {
  ruleId: string;
  section: string;
  passed: number;
  failed: number;
  rate: number;
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
}

export interface CoFailure {
  ruleA: string;
  ruleB: string;
  coOccurrenceRate: number;
}

export interface RuleComplianceMatrix {
  rules: RuleComplianceEntry[];
  coFailures: CoFailure[];
}

export interface FrictionPattern {
  description: string;
  count: number;
  exampleThreadIds: string[];
}

export interface FrictionAnalysis {
  totalFrictionTurns: number;
  byCause: Record<string, number>;
  recoveryQuality: Record<string, number>;
  avgTurnsByVerdict: Record<string, number>;
  topPatterns: FrictionPattern[];
}

export interface AdversarialCategoryResult {
  category: string;
  passed: number;
  total: number;
  passRate: number;
}

export interface AdversarialDifficultyResult {
  difficulty: string;
  passed: number;
  total: number;
}

export interface AdversarialBreakdown {
  byCategory: AdversarialCategoryResult[];
  byDifficulty: AdversarialDifficultyResult[];
}

export interface TranscriptMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface RuleViolation {
  ruleId: string;
  evidence: string;
}

export interface FrictionTurn {
  turn: number;
  cause: 'bot' | 'user';
  description: string;
}

export interface ExemplarThread {
  threadId: string;
  compositeScore: number;
  intentAccuracy: number | null;
  correctnessVerdict: string | null;
  efficiencyVerdict: string | null;
  taskCompleted: boolean;
  transcript: TranscriptMessage[];
  ruleViolations: RuleViolation[];
  frictionTurns: FrictionTurn[];
}

export interface Exemplars {
  best: ExemplarThread[];
  worst: ExemplarThread[];
}

export interface ProductionPrompts {
  intentClassification: string | null;
  mealSummarySpec: string | null;
}

export interface TopIssue {
  rank: number;
  area: string;
  description: string;
  affectedCount: number;
  exampleThreadId: string | null;
}

export interface ExemplarAnalysis {
  threadId: string;
  type: 'good' | 'bad';
  whatHappened: string;
  why: string;
  promptGap: string | null;
}

export interface PromptGap {
  promptSection: string;
  evalRule: string;
  gapType: 'UNDERSPEC' | 'SILENT' | 'LEAKAGE' | 'CONFLICTING';
  description: string;
  suggestedFix: string;
}

export interface Recommendation {
  priority: 'P0' | 'P1' | 'P2';
  area: string;
  action: string;
  estimatedImpact: string;
}

export interface NarrativeOutput {
  executiveSummary: string;
  topIssues: TopIssue[];
  exemplarAnalysis: ExemplarAnalysis[];
  promptGaps: PromptGap[];
  recommendations: Recommendation[];
}

export interface ReportMetadata {
  runId: string;
  runName: string | null;
  appId: string;
  evalType: string;
  createdAt: string;
  llmProvider: string | null;
  llmModel: string | null;
  totalThreads: number;
  completedThreads: number;
  errorThreads: number;
  durationMs: number | null;
  dataPath: string | null;
}

export interface ReportPayload {
  metadata: ReportMetadata;
  healthScore: HealthScore;
  distributions: VerdictDistributions;
  ruleCompliance: RuleComplianceMatrix;
  friction: FrictionAnalysis;
  adversarial: AdversarialBreakdown | null;
  exemplars: Exemplars;
  productionPrompts: ProductionPrompts;
  narrative: NarrativeOutput | null;
}
```

---

## Step 6: Frontend — API Client (`src/services/api/reportsApi.ts`)

```typescript
import { apiRequest } from './client';
import type { ReportPayload } from '@/types/reports';

export const reportsApi = {
  /**
   * Fetch the full report for a completed eval run.
   * May take 10-30s on first call (LLM narrative generation).
   */
  fetchReport: (runId: string): Promise<ReportPayload> =>
    apiRequest<ReportPayload>(`/api/reports/${runId}`),
};
```

### Register in barrel export:
Add to `src/services/api/index.ts`:
```typescript
export { reportsApi } from './reportsApi';
```

---

## Step 7: Backend — `prompts/` Directory Scaffold

Create empty files for Phase 3:

```
backend/app/services/reports/prompts/__init__.py      # empty
backend/app/services/reports/prompts/narrative_prompt.py  # empty, Phase 3
backend/app/services/reports/prompts/production_prompts.py  # empty, Phase 3
```

---

## Verification Checklist

- [ ] `backend/app/services/reports/` directory exists with `__init__.py`, `report_service.py`, `schemas.py`, `health_score.py`
- [ ] `backend/app/services/reports/prompts/` directory exists with `__init__.py`
- [ ] `backend/app/routes/reports.py` exists and is registered in `main.py`
- [ ] `GET /api/reports/{some-run-id}` returns valid JSON (even if mostly empty/stub)
- [ ] `src/types/reports.ts` compiles with `npx tsc -b`
- [ ] `src/services/api/reportsApi.ts` compiles and is exported from barrel
- [ ] Health score function returns correct grade for known inputs (manual test)
- [ ] Router count in `main.py` comment updated from 15 to 16

## Dependencies

- No new pip packages required
- No new npm packages required
- Uses only existing: SQLAlchemy, FastAPI, jsPDF, Recharts
