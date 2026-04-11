# Analytics Platform — Execution Prompt

> Copy this entire prompt into a new Claude Code session to execute the implementation.

---

## Prompt

```
You are implementing the Analytics Platform for this evaluation platform. This is a multi-phase implementation that must be executed faithfully using the subagent-driven development workflow.

## Required Reading (READ THESE FIRST, DO NOT SKIP)

Before touching ANY code, read these two documents completely:

1. **Design Spec (WHY):** `docs/plans/analytics-platform-spec.md`
   - Explains every decision, the before/after, why things are designed this way
   - Read sections 1-4 carefully — they explain the data model, population pipeline, and generic design
   - Section 10 shows before/after scenarios — this is your acceptance criteria

2. **Implementation Plan (HOW):** `docs/plans/analytics-platform-plan.md`
   - DDLs, ORM models, file paths, code patterns, execution order
   - Section 11 shows the execution phases — follow this order exactly
   - Contains exact SQL for table creation, exact Python patterns for extractors

3. **Existing code context:** Read `CLAUDE.md` at the repo root for codebase conventions.

## Execution Method

Use `superpowers:subagent-driven-development` to execute this plan task-by-task. Each task below is a discrete unit of work dispatched to a fresh subagent.

## CRITICAL RULES — VIOLATIONS ARE UNACCEPTABLE

### No Hardcoding
- NEVER hardcode app names (kaira-bot, voice-rx, inside-sales) in any file
- NEVER hardcode evaluator names or types as constants
- ALL app context derived from `eval_runs.app_id` or `App.config`
- ALL evaluator identity from the source data, never assumed
- If you see yourself writing an if/else for a specific app name, STOP — you're doing it wrong

### Generic Architecture
- Class/method/function/file names must be generic: `FactPopulator`, `extract_eval_facts`, `analytics_session` — NOT `KairaFactPopulator`, `extract_kaira_rules`, `kaira_analytics`
- The extractor registry pattern (`EXTRACTORS = {"batch_thread": ..., "call_quality": ...}`) dispatches by `eval_type`, not by app name
- Adding a new eval_type = adding one extractor file + one registry entry. Zero changes to existing code.

### Separation of Concerns
- Extractors do NOT touch the database. They receive data, return `FactSet` dataclasses.
- `FactPopulator` handles DB operations (delete old facts, bulk insert new).
- Job submission is a one-liner in each runner — no business logic at the trigger point.
- Tool logging wraps `dispatch_tool_call` — no per-tool logging code.
- Cache is a layer in `sql_agent.py` — transparent to callers.

### Code Quality
- Follow existing codebase patterns: async SQLAlchemy, Pydantic models, `CamelModel` for API schemas
- Use `TenantUserMixin` on all new models that need tenant/user scoping
- Use existing `Base` from `app.models.base` for all ORM models
- Imports at function level for circular dependency avoidance (match existing pattern in `tool_handlers.py`)
- All DB operations wrapped in try/except with meaningful error messages
- Type hints on all function signatures

## Tasks

### Task 1: Database Migration — Create 6 Tables

**Files:**
- Create: `alembic/versions/xxxx_add_analytics_tables.py` (or use the project's migration tool)
- If the project doesn't use Alembic, create raw SQL migration file

**Tables to create (exact DDL in analytics-platform-plan.md Section 1 + Sections 3-5):**
1. `analytics_run_facts` — one row per eval run
2. `analytics_eval_facts` — one row per evaluator per thread
3. `analytics_criterion_facts` — one row per criterion per thread
4. `analytics_jobs` — analytics job execution logs
5. `agent_tool_logs` — chat assistant tool call logs
6. `analytics_query_cache` — SQL agent result cache

**After creating migration, run it against the local Docker PostgreSQL:**
```bash
docker compose exec backend python -c "
from app.database import engine
from app.models.base import Base
import asyncio
asyncio.run(Base.metadata.create_all(bind=engine))
"
```
Or use the project's standard migration approach.

**Verify:** Connect to DB and confirm all 6 tables exist with correct columns.

### Task 2: ORM Models

**Files:**
- Create: `backend/app/models/analytics_facts.py` — `AnalyticsRunFact`, `AnalyticsEvalFact`, `AnalyticsCriterionFact`
- Create: `backend/app/models/analytics_log.py` — `AnalyticsJobLog`, `AgentToolLog`, `AnalyticsQueryCache`

**Rules:**
- Use `Base` from `app.models.base`
- Use `mapped_column` pattern matching existing models (see `eval_run.py` for reference)
- JSONB columns use `from sqlalchemy.dialects.postgresql import JSONB`
- Add `__table_args__` with indexes matching the DDL
- Register models in `backend/app/models/__init__.py` if the project uses a central registry

**Verify:** 
```bash
docker compose exec backend python -c "
from app.models.analytics_facts import AnalyticsRunFact, AnalyticsEvalFact, AnalyticsCriterionFact
from app.models.analytics_log import AnalyticsJobLog, AgentToolLog, AnalyticsQueryCache
print('All models import OK')
"
```

### Task 3: Analytics Types + Extractor Interface

**Files:**
- Create: `backend/app/services/analytics/__init__.py` — `submit_analytics_job()` helper
- Create: `backend/app/services/analytics/types.py` — `FactSet`, `PopulationResult`, row dataclasses

**`FactSet` contains:**
```python
@dataclass
class RunFactRow:
    run_id: UUID
    app_id: str
    tenant_id: UUID
    user_id: UUID
    eval_type: str
    status: str
    created_at: datetime
    completed_at: datetime | None
    duration_ms: float | None
    thread_count: int
    pass_count: int
    fail_count: int
    error_count: int
    pass_rate: float | None
    avg_intent_accuracy: float | None
    adversarial_total: int | None
    adversarial_blocked: int | None
    adversarial_block_rate: float | None
    context: dict

@dataclass
class EvalFactRow:
    run_id: UUID
    app_id: str
    tenant_id: UUID
    eval_type: str
    item_id: str
    item_type: str
    evaluator_type: str
    evaluator_name: str
    evaluator_id: UUID | None
    result_status: str | None
    result_score: float | None
    result_verdict: str | None
    success: bool | None
    result_detail: dict
    context: dict
    created_at: datetime

@dataclass
class CriterionFactRow:
    run_id: UUID
    app_id: str
    tenant_id: UUID
    item_id: str
    criterion_source: str
    criterion_id: str
    criterion_label: str | None
    evaluator_type: str
    status: str
    passed: bool | None
    evidence: str | None
    created_at: datetime

@dataclass
class FactSet:
    run_fact: RunFactRow
    eval_facts: list[EvalFactRow]
    criterion_facts: list[CriterionFactRow]

@dataclass
class PopulationResult:
    run_id: UUID
    rows_inserted: int
    duration_ms: float
    errors: list[str]
```

**`submit_analytics_job` in `__init__.py`:**
- Creates a `Job` row with `job_type="populate-analytics"`, `priority=500`, `queue_class="analytics"`
- Params: `{"run_id": str(run_id), "app_id": app_id}`
- Does NOT commit — caller's transaction handles it

**Verify imports.**

### Task 4: Extractors — batch_thread

**Files:**
- Create: `backend/app/services/analytics/extractors/__init__.py` — registry dict
- Create: `backend/app/services/analytics/extractors/batch_thread.py`

**This extractor handles kaira-bot style batch evaluations.** But it must NOT reference kaira-bot by name. It reads from the generic `ThreadEvaluation` model.

**Extraction logic:**
1. Receives: `run: EvalRun`, `threads: list[ThreadEvaluation]`
2. For each thread, extracts:
   - One `EvalFactRow` for intent (evaluator_type='intent', result_score=thread.intent_accuracy)
   - One `EvalFactRow` for correctness (evaluator_type='correctness', result_status=thread.worst_correctness)
   - One `EvalFactRow` for efficiency (evaluator_type='efficiency', result_status=thread.efficiency_verdict)
   - One `EvalFactRow` per custom evaluator in `result.custom_evaluations`
   - `CriterionFactRow` for each rule in `result.correctness_evaluations[].rule_compliance[]`
   - `CriterionFactRow` for each rule in `result.efficiency_evaluation.rule_outcomes[]` (if present)
3. Aggregates into `RunFactRow` with pass/fail counts

**IMPORTANT:** Read the actual JSON structure from `docs/plans/analytics-platform-spec.md` Section 1 (under "What exists today") and the exploration data in the plan. The paths are:
- Rules: `result -> 'correctness_evaluations' -> [] -> 'rule_compliance' -> []`
- Each rule has: `rule_id`, `section`, `status` (FOLLOWED/VIOLATED/NOT_APPLICABLE), `followed`, `evidence`
- Custom evals: `result -> 'custom_evaluations' -> {evaluator_uuid: {output: {...}}}`

**Test against real data:**
```bash
docker compose exec backend python -c "
import asyncio
from app.database import async_session
from sqlalchemy import select, text
from app.models.eval_run import EvalRun, ThreadEvaluation
from app.services.analytics.extractors.batch_thread import extract_batch_thread

async def test():
    async with async_session() as db:
        # Find a batch_thread run
        r = await db.execute(text(\"\"\"
            SELECT e.id, e.app_id FROM eval_runs e
            WHERE e.eval_type = 'batch_thread' AND e.status = 'completed'
            ORDER BY e.created_at DESC LIMIT 1
        \"\"\"))
        row = r.first()
        if not row:
            print('No batch_thread runs found'); return
        
        run_id = row[0]
        run = await db.scalar(select(EvalRun).where(EvalRun.id == run_id))
        threads = (await db.execute(select(ThreadEvaluation).where(ThreadEvaluation.run_id == run_id))).scalars().all()
        
        fact_set = extract_batch_thread(run, threads)
        print(f'Run fact: pass_rate={fact_set.run_fact.pass_rate}, threads={fact_set.run_fact.thread_count}')
        print(f'Eval facts: {len(fact_set.eval_facts)}')
        print(f'Criterion facts: {len(fact_set.criterion_facts)}')
        for ef in fact_set.eval_facts[:3]:
            print(f'  {ef.evaluator_type}/{ef.evaluator_name}: status={ef.result_status} score={ef.result_score}')
        for cf in fact_set.criterion_facts[:3]:
            print(f'  {cf.criterion_id}: {cf.status} ({cf.criterion_source})')

asyncio.run(test())
"
```

### Task 5: Extractors — call_quality, adversarial, full_eval, custom

**Files:**
- Create: `backend/app/services/analytics/extractors/call_quality.py`
- Create: `backend/app/services/analytics/extractors/adversarial.py`
- Create: `backend/app/services/analytics/extractors/full_eval.py`
- Create: `backend/app/services/analytics/extractors/custom_eval.py`

**Each extractor follows the same pattern as batch_thread but reads different JSON paths.** See `analytics-platform-spec.md` Section 1 for the JSON structure per eval_type.

**call_quality:** Reads `result.evaluations[]` — each has `evaluator_id`, `evaluator_name`, `output`. One `EvalFactRow` per evaluator per thread. Context includes call metadata from `result.call_metadata`.

**adversarial:** Reads `AdversarialEvaluation` rows. One `EvalFactRow` per case (evaluator_type='adversarial_judge'). `CriterionFactRow` from `result.judge.ruleOutcomes[]` (note: camelCase in adversarial results).

**full_eval:** Reads `EvalRun.result` directly (no child rows). One `EvalFactRow` (evaluator_type='critique'). No criterion facts.

**custom:** Reads `EvalRun.result.output`. One `EvalFactRow` (evaluator_type='custom'). result_detail stores the full custom output. No criterion facts.

**Register all in `extractors/__init__.py`:**
```python
EXTRACTORS = {
    "batch_thread": extract_batch_thread,
    "call_quality": extract_call_quality,
    "batch_adversarial": extract_adversarial,
    "full_evaluation": extract_full_eval,
    "custom": extract_custom,
}
```

### Task 6: FactPopulator

**Files:**
- Create: `backend/app/services/analytics/fact_populator.py`

**This is the orchestrator. It:**
1. Loads the eval run by ID
2. Loads child evaluations (threads or adversarial cases) based on eval_type
3. Deletes existing facts for this run_id (idempotent re-run)
4. Dispatches to the correct extractor from the registry
5. Bulk inserts all fact rows
6. Creates/updates an `AnalyticsJobLog` row
7. Returns `PopulationResult`

**Pattern:**
```python
class FactPopulator:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def populate(self, run_id: UUID) -> PopulationResult:
        start = time.monotonic()
        log = AnalyticsJobLog(run_id=run_id, job_type="populate_facts", status="running", started_at=datetime.now(timezone.utc))
        self.db.add(log)
        
        try:
            run = await self._load_run(run_id)
            extractor = EXTRACTORS.get(run.eval_type)
            if not extractor:
                raise ValueError(f"No extractor for eval_type: {run.eval_type}")
            
            children = await self._load_children(run)
            fact_set = extractor(run, children)
            
            await self._delete_existing(run_id)
            rows = await self._bulk_insert(fact_set)
            
            log.status = "completed"
            log.rows_inserted = rows
            log.duration_ms = (time.monotonic() - start) * 1000
            log.completed_at = datetime.now(timezone.utc)
            await self.db.commit()
            
            return PopulationResult(run_id=run_id, rows_inserted=rows, ...)
        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)
            await self.db.commit()
            raise
```

**Test:**
```bash
docker compose exec backend python -c "
import asyncio
from app.database import async_session
from app.services.analytics.fact_populator import FactPopulator

async def test():
    async with async_session() as db:
        # Use a known completed run
        from sqlalchemy import text
        r = await db.execute(text(\"SELECT id FROM eval_runs WHERE status = 'completed' ORDER BY created_at DESC LIMIT 1\"))
        run_id = r.scalar()
        if not run_id:
            print('No completed runs'); return
        
        populator = FactPopulator(db)
        result = await populator.populate(run_id)
        print(f'Populated: {result.rows_inserted} rows in {result.duration_ms:.0f}ms')
        
        # Verify facts exist
        from app.models.analytics_facts import AnalyticsRunFact, AnalyticsEvalFact, AnalyticsCriterionFact
        from sqlalchemy import select, func
        for model, name in [(AnalyticsRunFact, 'run'), (AnalyticsEvalFact, 'eval'), (AnalyticsCriterionFact, 'criterion')]:
            count = await db.scalar(select(func.count(model.id)).where(model.run_id == run_id))
            print(f'  {name}_facts: {count} rows')

asyncio.run(test())
"
```

### Task 7: Job Wiring — Register + Trigger

**Files:**
- Modify: `backend/app/services/job_worker.py` — register `populate-analytics` in `get_job_submission_metadata()` and in the job runner dispatch
- Modify: `backend/app/services/evaluators/batch_runner.py` — add `submit_analytics_job()` after run completion
- Modify: `backend/app/services/evaluators/inside_sales_runner.py` — same
- Modify: `backend/app/services/evaluators/adversarial_runner.py` — same
- Modify: `backend/app/services/evaluators/voice_rx_runner.py` — same
- Modify: `backend/app/services/evaluators/custom_evaluator_runner.py` — same

**The trigger is ONE line in each runner, after the run is marked completed:**
```python
from app.services.analytics import submit_analytics_job
await submit_analytics_job(db=db, run_id=run_id, app_id=app_id, tenant_id=tenant_id, user_id=user_id)
```

**Read each runner file to find the exact completion point.** Look for where `status` is set to `completed` and `await db.commit()` is called. Add the submit call BEFORE the commit (so it's in the same transaction).

**The job runner entry point:**
```python
async def run_populate_analytics(job_id, params, db):
    from app.services.analytics.fact_populator import FactPopulator
    populator = FactPopulator(db)
    result = await populator.populate(UUID(params["run_id"]))
    return {"rows_inserted": result.rows_inserted, "duration_ms": result.duration_ms}
```

### Task 8: Agent Tool Logging

**Files:**
- Modify: `backend/app/services/report_builder/tool_handlers.py` — wrap `dispatch_tool_call` with timing + logging

**The wrapper:**
```python
async def dispatch_tool_call(tool_name, arguments, *, db, auth, app_id):
    import time
    start = time.monotonic()
    # ... existing dispatch logic ...
    # After getting result, log to agent_tool_logs (fire-and-forget)
    elapsed = (time.monotonic() - start) * 1000
    try:
        from app.models.analytics_log import AgentToolLog
        log = AgentToolLog(
            tenant_id=auth.tenant_id, user_id=auth.user_id, app_id=app_id,
            tool_name=tool_name, arguments=arguments,
            execution_ms=elapsed, status="ok" or "error",
            row_count=result.get("row_count") if isinstance(result, dict) else None,
            # For analyze tool: capture SQL details
            generated_sql=result.get("sql_used") if tool_name == "analyze" else None,
            cache_hit=result.get("cache_hit", False) if tool_name == "analyze" else False,
        )
        db.add(log)
    except Exception:
        pass  # Never fail the tool call because logging failed
```

### Task 9: Query Cache + SQL Agent Hardening

**Files:**
- Modify: `backend/app/services/chat_engine/sql_agent.py`

**Add three things:**

1. **Cache check before execution** — query `analytics_query_cache` by `(sql_hash, tenant_id, app_id)` where `expires_at > now()`
2. **Cache store after execution** — insert result with 120s TTL
3. **EXPLAIN cost check** — run `EXPLAIN (FORMAT JSON)` before executing, reject if cost > 50000
4. **Retry on error** — if SQL fails, send error to inner LLM for one fix attempt

### Task 10: Analytics Connection Pool

**Files:**
- Modify: `backend/app/database.py` — add `analytics_engine` + `analytics_session`
- Modify: `backend/app/config.py` — add `ANALYTICS_DATABASE_URL` (defaults to empty, falls back to primary)
- Modify: `backend/app/services/chat_engine/sql_agent.py` — use `analytics_session` for query execution

### Task 11: Updated Semantic Model

**Files:**
- Modify: `backend/app/services/chat_engine/semantic_model.yaml`

**Replace the thread_evaluations JSONB descriptions with fact table descriptions.** See analytics-platform-plan.md Section 7 for the exact YAML.

**Keep the existing `eval_runs` table in the model** — the SQL agent might still need it for fields not in the fact tables (like `batch_metadata`).

### Task 12: Backfill Script

**Files:**
- Create: `backend/scripts/backfill_analytics_facts.py`

**The script:**
1. Queries all completed eval_runs (optionally filtered by `--app-id` or `--run-id`)
2. For each run, calls `FactPopulator.populate(run_id)`
3. Logs progress
4. Handles errors per-run (doesn't stop on one failure)

### Task 13: End-to-End Verification

**This is the acceptance test. Run it against the local Docker PostgreSQL.**

```bash
docker compose exec backend python -c "
import asyncio, json

async def e2e_test():
    from app.database import async_session
    from sqlalchemy import select, func, text
    from app.services.analytics.fact_populator import FactPopulator
    from app.models.analytics_facts import AnalyticsRunFact, AnalyticsEvalFact, AnalyticsCriterionFact
    from app.services.chat_engine.sql_agent import analyze

    async with async_session() as db:
        # 1. Find a completed run
        r = await db.execute(text(\"\"\"
            SELECT e.id, e.app_id, e.eval_type, t.name
            FROM eval_runs e JOIN tenants t ON e.tenant_id = t.id
            WHERE e.status = 'completed'
            ORDER BY e.created_at DESC LIMIT 1
        \"\"\"))
        row = r.first()
        if not row:
            print('FAIL: No completed runs in DB'); return
        run_id, app_id, eval_type, tenant_name = row
        print(f'Test run: {str(run_id)[:8]} app={app_id} type={eval_type} tenant={tenant_name}')

        # 2. Populate facts
        populator = FactPopulator(db)
        result = await populator.populate(run_id)
        print(f'Populated: {result.rows_inserted} rows in {result.duration_ms:.0f}ms')

        # 3. Verify fact counts
        for model, name in [(AnalyticsRunFact, 'run'), (AnalyticsEvalFact, 'eval'), (AnalyticsCriterionFact, 'criterion')]:
            count = await db.scalar(select(func.count(model.id)).where(model.run_id == run_id))
            print(f'  {name}_facts: {count} rows')
            assert count > 0 or name == 'criterion', f'FAIL: {name}_facts is empty'

        # 4. Test SQL agent queries against fact tables
        r2 = await db.execute(text(f\"SELECT id, tenant_id, user_id FROM eval_runs WHERE id = '{run_id}'\"))
        run_row = r2.first()
        class Auth:
            tenant_id = str(run_row[1])
            user_id = str(run_row[2])
            is_owner = True
            app_access = frozenset([app_id])

        queries = [
            'What is the pass rate for the most recent run?',
            'How many total runs and threads have been evaluated?',
        ]
        
        # Only test rule query if we have criterion facts
        crit_count = await db.scalar(select(func.count(AnalyticsCriterionFact.id)).where(AnalyticsCriterionFact.run_id == run_id))
        if crit_count > 0:
            queries.append('Which rules have the lowest compliance rate?')

        for q in queries:
            print(f'\\nQ: {q}')
            result = await analyze(question=q, db=db, auth=Auth(), app_id=app_id)
            if result['status'] == 'ok':
                print(f'  OK: {result[\"row_count\"]} rows')
                for row in result['data'][:2]:
                    print(f'    {row}')
            else:
                print(f'  FAIL: {result.get(\"error\", \"\")[:100]}')

        # 5. Verify idempotency — re-populate should not duplicate
        result2 = await populator.populate(run_id)
        count_after = await db.scalar(select(func.count(AnalyticsEvalFact.id)).where(AnalyticsEvalFact.run_id == run_id))
        count_before = len([ef for ef in result.eval_facts] if hasattr(result, 'eval_facts') else 0)
        print(f'\\nIdempotency: re-populated {result2.rows_inserted} rows, total eval_facts={count_after}')

        print('\\n=== ALL TESTS PASSED ===')

asyncio.run(e2e_test())
"
```

## Post-Implementation Checklist

After all tasks are complete, verify:

- [ ] All 6 tables exist in the database with correct columns and indexes
- [ ] All ORM models import without errors
- [ ] FactPopulator successfully populates facts for at least one completed run of each eval_type that has data
- [ ] Re-running populate for the same run_id produces identical results (idempotency)
- [ ] SQL agent's semantic model points at fact tables
- [ ] SQL agent can answer "which rules fail most?" using fact tables (no JSONB lateral joins)
- [ ] Query cache stores and retrieves results
- [ ] EXPLAIN cost check rejects expensive queries
- [ ] Agent tool logs capture tool calls
- [ ] Analytics job log captures population metadata
- [ ] `populate-analytics` job type is registered and runnable by the worker
- [ ] At least one eval runner has the `submit_analytics_job()` trigger
- [ ] Backfill script successfully processes existing completed runs
- [ ] No hardcoded app names anywhere in analytics code
- [ ] All new files use generic names
- [ ] TypeScript build still passes (`npx tsc --noEmit`)
- [ ] Python tests still pass (`PYTHONPATH=backend python -m pytest backend/tests/ -q`)
```
