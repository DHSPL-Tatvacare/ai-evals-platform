# Phase 4 — Services

Backend services that run outside the request-response cycle (job workers, runners, report generators) need tenant/user context threaded through.

## 4.1 Job Worker (`backend/app/services/job_worker.py`)

### Current Problem

The worker picks up jobs and dispatches to handlers with no user context. Handlers create `EvalRun` records with `user_id="default"`.

### Solution: Read Auth from Job Params

The job submission route (Phase 3) injects `tenant_id` and `user_id` into `job.params`. The worker reads them and passes them through.

### Changes

#### `process_job()` — Extract Auth from Params

```python
async def process_job(job_id: str, job_type: str, params: dict):
    tenant_id = uuid.UUID(params["tenant_id"])
    user_id = uuid.UUID(params["user_id"])

    # Pass to handler
    handler = JOB_HANDLERS.get(job_type)
    if not handler:
        raise ValueError(f"Unknown job type: {job_type}")
    await handler(job_id, params, tenant_id=tenant_id, user_id=user_id)
```

#### All Handler Signatures — Add `tenant_id, user_id`

```python
async def handle_evaluate_batch(job_id, params, *, tenant_id: uuid.UUID, user_id: uuid.UUID):
    await batch_runner.run_batch_evaluation(
        job_id=job_id,
        tenant_id=tenant_id,
        user_id=user_id,
        **extract_runner_params(params),
    )
```

Same for all 5 handlers:
- `handle_evaluate_batch`
- `handle_evaluate_adversarial`
- `handle_evaluate_voice_rx`
- `handle_evaluate_custom`
- `handle_evaluate_custom_batch`

#### `recover_stale_jobs()` — No Change Needed

Stale recovery just marks jobs as failed. It doesn't create data. No auth context required.

#### `recover_stale_eval_runs()` — No Change Needed

Same reasoning — just status reconciliation.

#### `is_job_cancelled()` — Add Ownership Check

Currently checks by job_id only. Add tenant_id filter:

```python
async def is_job_cancelled(job_id: str, tenant_id: uuid.UUID) -> bool:
    # In-memory check (no change)
    if job_id in _cancelled_jobs:
        return True
    # DB fallback — add tenant_id
    async with async_session() as db:
        job = await db.scalar(
            select(Job).where(Job.id == job_id, Job.tenant_id == tenant_id)
        )
        return job and job.status == "cancelled"
```

---

## 4.2 Runner Utilities (`backend/app/services/evaluators/runner_utils.py`)

### `create_eval_run()` — Add tenant_id, user_id

```python
async def create_eval_run(
    *,
    id: uuid.UUID,
    tenant_id: uuid.UUID,      # NEW
    user_id: uuid.UUID,         # NEW
    app_id: str,
    eval_type: str,
    job_id,
    listing_id: ...,
    session_id: ...,
    evaluator_id: ...,
    llm_provider: ...,
    llm_model: ...,
    batch_metadata: ...,
) -> None:
    db.add(EvalRun(
        id=id,
        tenant_id=tenant_id,
        user_id=user_id,
        app_id=app_id,
        eval_type=eval_type,
        # ... rest unchanged
    ))
```

### `finalize_eval_run()` — Add Tenant Check

```python
async def finalize_eval_run(
    run_id: uuid.UUID,
    tenant_id: uuid.UUID,      # NEW
    *,
    status: str,
    duration_ms: float,
    ...
) -> None:
    condition = and_(
        EvalRun.id == run_id,
        EvalRun.tenant_id == tenant_id,  # Ensure we only update our own
    )
    if status != "cancelled":
        condition = condition & (EvalRun.status != "cancelled")
    await db.execute(update(EvalRun).where(condition).values(**values))
```

### `save_api_log()` — No Model Change (Unchanged)

ApiLog has no tenant_id/user_id columns (access controlled via parent EvalRun). No changes needed to the function signature. The `run_id` FK already provides the chain of custody.

---

## 4.3 Batch Runner (`backend/app/services/evaluators/batch_runner.py`)

### Signature Change

```python
async def run_batch_evaluation(
    job_id,
    tenant_id: uuid.UUID,      # NEW
    user_id: uuid.UUID,         # NEW
    data_path: ...,
    csv_content: ...,
    app_id: str = "kaira-bot",
    ...
) -> dict:
```

### EvalRun Creation

```python
await create_eval_run(
    id=run_id,
    tenant_id=tenant_id,
    user_id=user_id,
    app_id=app_id,
    eval_type="batch_thread",
    ...
)
```

### Evaluator Lookup — Add Ownership Check

```python
# When loading custom evaluators, verify ownership or system
evaluator = await db.scalar(
    select(Evaluator).where(
        Evaluator.id == evaluator_id,
        or_(
            and_(Evaluator.tenant_id == tenant_id, Evaluator.user_id == user_id),
            Evaluator.tenant_id == SYSTEM_TENANT_ID,
        ),
    )
)
if not evaluator:
    raise ValueError(f"Evaluator {evaluator_id} not found or not accessible")
```

### Pass tenant_id Through to `finalize_eval_run()`

```python
await finalize_eval_run(run_id, tenant_id, status="completed", ...)
```

### Cancellation Checks

```python
if await is_job_cancelled(job_id, tenant_id):
    ...
```

---

## 4.4 Voice-RX Runner (`backend/app/services/evaluators/voice_rx_runner.py`)

### Signature Change

```python
async def run_voice_rx_evaluation(job_id, params: dict, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> dict:
```

Or extract from params within the function (consistent with current pattern):

```python
async def run_voice_rx_evaluation(job_id, params: dict) -> dict:
    tenant_id = uuid.UUID(params["tenant_id"])
    user_id = uuid.UUID(params["user_id"])
```

**Decision:** Use explicit kwargs for type safety. The handler in `job_worker.py` extracts and passes them.

### Default Prompt/Schema Loading

System prompts use `SYSTEM_TENANT_ID`:

```python
async def _load_default_prompt(app_id: str, prompt_type: str, source_type: str) -> str:
    result = await db.execute(
        select(Prompt).where(
            Prompt.tenant_id == SYSTEM_TENANT_ID,  # System defaults
            Prompt.app_id == app_id,
            Prompt.prompt_type == prompt_type,
            Prompt.source_type == source_type,
        )
    )
```

### Listing/Session Lookup — Ownership Check

```python
listing = await db.scalar(
    select(Listing).where(
        Listing.id == listing_id,
        Listing.tenant_id == tenant_id,
        Listing.user_id == user_id,
    )
)
if not listing:
    raise ValueError(f"Listing {listing_id} not found or not accessible")
```

### EvalRun and Finalization

Pass `tenant_id, user_id` to `create_eval_run()` and `finalize_eval_run()`.

---

## 4.5 Custom Evaluator Runner (`backend/app/services/evaluators/custom_evaluator_runner.py`)

### Signature Change

```python
async def run_custom_evaluator(job_id, params: dict, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> dict:

async def run_custom_eval_batch(job_id, params: dict, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> dict:
```

### All Lookups — Ownership Check

```python
evaluator = await db.scalar(
    select(Evaluator).where(
        Evaluator.id == evaluator_id,
        or_(
            and_(Evaluator.tenant_id == tenant_id, Evaluator.user_id == user_id),
            Evaluator.tenant_id == SYSTEM_TENANT_ID,
        ),
    )
)

listing = await db.scalar(
    select(Listing).where(
        Listing.id == listing_id,
        Listing.tenant_id == tenant_id,
        Listing.user_id == user_id,
    )
)
```

---

## 4.6 Adversarial Runner (`backend/app/services/evaluators/adversarial_runner.py`)

### Signature Change

```python
async def run_adversarial_evaluation(
    job_id,
    tenant_id: uuid.UUID,      # NEW — from auth, not client params
    user_id: uuid.UUID,         # NEW — from auth, not client params
    kaira_api_url: str = "",
    kaira_auth_token: str = "",
    ...
) -> dict:
```

### Config Loading — User-Scoped

```python
config = await load_config_from_db(tenant_id=tenant_id, user_id=user_id)
# Falls back to system default if user has no custom config
```

### Kaira Client User ID

The `user_id` passed to `KairaClient.stream_message()` is the **external Kaira test user** (`KAIRA_TEST_USER_ID`), NOT the authenticated user. Keep this distinct:

```python
kaira_test_user_id = params.get("kaira_test_user_id", settings.KAIRA_TEST_USER_ID)
# This is the user ID sent to the Kaira API for testing — NOT the auth user
```

---

## 4.7 Adversarial Config (`backend/app/services/evaluators/adversarial_config.py`)

### `load_config_from_db()` — Add Scoping

```python
async def load_config_from_db(tenant_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    async with async_session() as db:
        # Try user-specific config first
        result = await db.scalar(
            select(Setting).where(
                Setting.tenant_id == tenant_id,
                Setting.user_id == user_id,
                Setting.app_id == SETTINGS_APP_ID,
                Setting.key == SETTINGS_KEY,
            )
        )
        if result:
            return result.value

        # Fall back to system default
        result = await db.scalar(
            select(Setting).where(
                Setting.tenant_id == SYSTEM_TENANT_ID,
                Setting.app_id == SETTINGS_APP_ID,
                Setting.key == SETTINGS_KEY,
            )
        )
        return result.value if result else get_default_config()
```

### `save_config_to_db()` — Add Scoping

```python
async def save_config_to_db(config: dict, tenant_id: uuid.UUID, user_id: uuid.UUID):
    async with async_session() as db:
        # Upsert user-specific config
        await db.execute(
            insert(Setting).values(
                tenant_id=tenant_id,
                user_id=user_id,
                app_id=SETTINGS_APP_ID,
                key=SETTINGS_KEY,
                value=config,
            ).on_conflict_do_update(
                constraint="uq_setting",
                set_={"value": config, "updated_at": func.now()},
            )
        )
        await db.commit()
```

---

## 4.8 Settings Helper (`backend/app/services/evaluators/settings_helper.py`)

### `get_llm_settings_from_db()` — Add Tenant/User Scoping

```python
async def get_llm_settings_from_db(
    tenant_id: uuid.UUID,         # NEW — required
    user_id: uuid.UUID,           # NEW — required
    app_id: Optional[str] = None,
    key: str = "llm-settings",
    auth_intent: Literal["managed_job", "interactive"] = "interactive",
    provider_override: Optional[str] = None,
) -> dict:
    async with async_session() as db:
        resolved_app_id = app_id or ""
        query = select(Setting).where(
            Setting.tenant_id == tenant_id,
            Setting.user_id == user_id,
            Setting.key == key,
            Setting.app_id == resolved_app_id,
        )
        result = await db.execute(query)
        setting = result.scalar_one_or_none()
        # ... rest of processing unchanged
```

**No fallback to `user_id="default"`.** If user hasn't configured LLM settings, the function returns empty/error. Frontend must prompt user to configure.

### All Callers Updated

Every call site must now pass `tenant_id` and `user_id`:

- `routes/llm.py` — from `auth` context
- `routes/reports.py` — from `auth` context
- `batch_runner.py` — from job params
- `voice_rx_runner.py` — from job params
- `custom_evaluator_runner.py` — from job params
- `adversarial_runner.py` — from job params
- `report_service.py` — from caller

---

## 4.9 Report Service (`backend/app/services/reports/report_service.py`)

### Constructor — Add Auth Context

```python
class ReportService:
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id
```

### `_load_run()` — Ownership Check

```python
async def _load_run(self, run_id: str) -> EvalRun:
    run = await self.db.scalar(
        select(EvalRun).where(
            EvalRun.id == run_id,
            EvalRun.tenant_id == self.tenant_id,
            EvalRun.user_id == self.user_id,
        )
    )
    if not run:
        raise ValueError(f"Run {run_id} not found or not accessible")
    return run
```

### Analytics Caching — Tenant Scoped

```python
# Cache writes include tenant_id
analytics = EvaluationAnalytics(
    tenant_id=self.tenant_id,
    app_id=run.app_id,
    scope="single_run",
    run_id=run.id,
    analytics_data=report_data,
)
```

---

## 4.10 Seed Defaults (`backend/app/services/seed_defaults.py`)

### All Seeds Use System Tenant/User

Replace every `user_id="default"` with:

```python
tenant_id=SYSTEM_TENANT_ID
user_id=SYSTEM_USER_ID
```

### Prompts

```python
Prompt(
    app_id="voice-rx",
    prompt_type="transcription",
    version=1,
    name="Default Transcription Prompt",
    prompt="...",
    is_default=True,
    source_type="system",
    tenant_id=SYSTEM_TENANT_ID,
    user_id=SYSTEM_USER_ID,
)
```

### Schemas — Same Pattern

### Evaluators

```python
Evaluator(
    app_id="voice-rx",
    name="Accuracy",
    prompt="...",
    is_global=True,
    tenant_id=SYSTEM_TENANT_ID,
    user_id=SYSTEM_USER_ID,
)
```

### Idempotency Checks — Update Filters

```python
# Old:
select(Prompt).where(Prompt.app_id == "voice-rx", Prompt.user_id == "default")

# New:
select(Prompt).where(Prompt.app_id == "voice-rx", Prompt.tenant_id == SYSTEM_TENANT_ID)
```

---

## 4.11 Parallel Engine (`backend/app/services/evaluators/parallel_engine.py`)

If this file exists and orchestrates parallel evaluation:

- Pass `tenant_id, user_id` through to all `create_eval_run()` calls
- Pass through to `finalize_eval_run()` calls
- No direct DB queries in engine — it delegates to runners

---

## 4.12 LLM Providers (`backend/app/services/evaluators/llm_base.py`)

**No changes needed.** LLM providers are stateless — they receive an API key and model name. Auth context doesn't flow into the LLM call itself. The API key is resolved upstream by `settings_helper.py`.

---

## 4.13 Files Summary

| File | Action | Key Changes |
|------|--------|-------------|
| `services/job_worker.py` | MODIFY | Extract tenant_id/user_id from params; pass to handlers |
| `services/evaluators/runner_utils.py` | MODIFY | Add tenant_id/user_id to create_eval_run, finalize_eval_run |
| `services/evaluators/batch_runner.py` | MODIFY | Accept tenant_id/user_id; ownership checks |
| `services/evaluators/voice_rx_runner.py` | MODIFY | Accept tenant_id/user_id; use SYSTEM_TENANT_ID for defaults |
| `services/evaluators/custom_evaluator_runner.py` | MODIFY | Accept tenant_id/user_id; ownership checks |
| `services/evaluators/adversarial_runner.py` | MODIFY | Accept tenant_id/user_id; scoped config loading |
| `services/evaluators/adversarial_config.py` | MODIFY | Add tenant_id/user_id to load/save |
| `services/evaluators/settings_helper.py` | MODIFY | Add tenant_id/user_id params; remove fallbacks |
| `services/reports/report_service.py` | MODIFY | Accept tenant_id/user_id; ownership checks |
| `services/seed_defaults.py` | MODIFY | Use SYSTEM_TENANT_ID/SYSTEM_USER_ID; bootstrap admin |
| `services/evaluators/llm_base.py` | NO CHANGE | Stateless; no auth context needed |
