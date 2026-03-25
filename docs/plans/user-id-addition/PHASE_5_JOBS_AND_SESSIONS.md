# Phase 5: Job Worker & Session Integrity

## Goal

Background jobs execute in the context of the user who submitted them. The worker resolves per-user credentials, respects user ownership, and maintains clean DB session boundaries. After this phase, the full auth system is end-to-end.

**Prerequisite:** Phases 2 and 3 complete (user-scoped data + per-user settings).

---

## 5.1 — User Context in Job Params

### Current Job Creation Pattern

```python
# In route handlers:
job = Job(
    job_type="evaluate-batch",
    params={"app_id": "voice-rx", "run_id": str(run_id), ...},
    status="queued",
)
```

### New Pattern

```python
job = Job(
    job_type="evaluate-batch",
    params={"app_id": "voice-rx", "run_id": str(run_id), ...},
    user_id=current_user.id,     # Already set via UserMixin from Phase 2
    status="queued",
)
```

The `user_id` is persisted on the `Job` row via the `UserMixin` FK (Phase 2). The worker reads it when processing.

Additionally, embed `user_id` in `params` dict for convenience in handlers:

```python
params={
    "app_id": "voice-rx",
    "run_id": str(run_id),
    "user_id": str(current_user.id),  # Redundant but convenient for handlers
    ...
}
```

This redundancy means handlers don't need to re-query the Job row to get the user_id.

---

## 5.2 — Worker Loop: No Auth Changes Needed

**File:** `backend/app/services/job_worker.py`

The worker loop (`worker_loop()`) uses `async_session()` directly — not FastAPI dependencies. It doesn't need auth headers or cookies. It runs as a trusted server-side process.

### Current Flow (preserved)

```
worker_loop() → polls for queued jobs → process_job(job_id, job_type, params)
```

The worker doesn't authenticate as a user. It simply reads `user_id` from the job record or params and uses it for:
1. Resolving the user's LLM credentials (from settings table).
2. Writing results scoped to that user.
3. Creating eval_run / thread_evaluation rows with the correct `user_id`.

**No middleware, no JWT, no cookies in the worker.**

---

## 5.3 — Handler Credential Resolution

### Current Pattern (in runners)

Runners currently read LLM settings from the DB without user scoping:

```python
# Conceptual (varies by runner):
settings = await db.execute(
    select(Setting).where(Setting.key == "llm-settings")
)
api_key = settings.value.get("geminiApiKey")
provider = create_llm_provider("gemini", api_key=api_key, ...)
```

### New Pattern

Each handler extracts `user_id` from params and resolves that user's credentials:

```python
async def handle_evaluate_batch(job_id, params):
    user_id = uuid.UUID(params["user_id"])
    app_id = params["app_id"]

    async with async_session() as db:
        # Resolve user's LLM settings (Phase 3 helper)
        llm_settings = await get_llm_settings(db, app_id, user_id)

        if not llm_settings:
            raise ValueError("User has no LLM settings configured")

        api_key = llm_settings.get("geminiApiKey") or llm_settings.get("openaiApiKey")
        provider = llm_settings.get("provider", "gemini")
        model = llm_settings.get("selectedModel")

        llm = create_llm_provider(provider, api_key=api_key, model_name=model)
        # ... rest of handler
```

### Service Account Override

For Gemini service account mode:
- If the server has `GEMINI_SERVICE_ACCOUNT_PATH` configured, the worker uses it for all users' Gemini jobs (it's a server-level credential).
- The user's `geminiAuthMethod` setting determines whether to use their API key or the server's service account.
- Logic: `if user_settings.get("geminiAuthMethod") == "service_account" and settings.GEMINI_SERVICE_ACCOUNT_PATH: use_service_account()`.

---

## 5.4 — Result Ownership

When handlers create results (eval_runs, thread_evaluations, etc.), they must set `user_id`:

### Current Pattern

```python
eval_run = EvalRun(
    app_id=app_id,
    listing_id=listing_id,
    eval_type="batch_thread",
    # user_id defaults to "default" via UserMixin
)
```

### New Pattern

```python
eval_run = EvalRun(
    app_id=app_id,
    listing_id=listing_id,
    eval_type="batch_thread",
    user_id=user_id,       # From job params
)
```

**Apply to all models created by handlers:**
- `EvalRun`
- `ThreadEvaluation`
- `AdversarialEvaluation`
- `ApiLog`
- `Listing` (if created by batch jobs)
- `ChatSession` / `ChatMessage` (if created by adversarial evaluator)

### Verification Rule

Before a handler creates any row, assert that `user_id` is set:
```python
assert user_id is not None, "Handler must have user_id from job params"
```

---

## 5.5 — Job Cancellation: User Scoping

### Current Cancel Route

```python
@router.post("/{job_id}/cancel")
async def cancel_job(job_id: UUID, db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job.status = "cancelled"
    await db.commit()
    mark_job_cancelled(job_id)
```

### New Pattern

```python
@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = job.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")
    # ... rest unchanged
```

User can only cancel their own jobs. Admin can cancel any job (check role).

---

## 5.6 — Recovery: User Context

### `recover_stale_jobs()`

No changes needed — this operates on all stale jobs regardless of owner. It's a server-level maintenance task.

### `recover_stale_eval_runs()`

Same — operates across all users. Admin-level maintenance.

These functions run in the lifespan startup, before any user context exists.

---

## 5.7 — DB Session Discipline in Workers

### Current Pattern (correct, preserve it)

Workers use `async with async_session() as db:` for scoped sessions. Each handler gets its own session.

### Rules (enforced by code review, not changed architecturally)

1. **One session per logical unit of work.** Don't share sessions across handlers.
2. **Commit after each meaningful write.** Don't batch unrelated writes in one commit.
3. **Don't hold sessions open during LLM calls.** Open session → read params → close session → call LLM → open session → write results.
4. **Progress updates use their own mini-session** (via `update_job_progress()` — already does this).

### Anti-Pattern to Avoid

```python
# BAD: Session held open during LLM call
async with async_session() as db:
    listing = await db.get(Listing, listing_id)
    result = await llm.generate(listing.text)  # Minutes-long call!
    eval_run.result = result
    await db.commit()
```

```python
# GOOD: Separate sessions for read and write
async with async_session() as db:
    listing = await db.get(Listing, listing_id)
    text = listing.text  # Extract what you need

result = await llm.generate(text)  # No session held

async with async_session() as db:
    eval_run = await db.get(EvalRun, run_id)
    eval_run.result = result
    await db.commit()
```

This is already mostly followed in the codebase. Document it as a rule.

---

## 5.8 — Frontend: Job Polling User Scoping

**File:** `src/services/api/jobPolling.ts`

No changes needed to polling logic. The backend's `GET /api/jobs/{id}` is already scoped by `user_id` (Phase 2). If user A tries to poll user B's job, they get a 404.

The `submitAndPollJob()` flow:
1. Frontend `POST /api/jobs` → backend sets `user_id` from auth → returns job.
2. Frontend polls `GET /api/jobs/{id}` → backend checks `user_id` → returns or 404.

All transparent. No frontend changes.

---

## 5.9 — Concurrent User Jobs

### Question: Can multiple users run jobs simultaneously?

**Yes.** The worker loop processes one job at a time (sequential), but jobs from different users are interleaved in the queue. The `order_by(Job.created_at)` ensures FIFO regardless of user.

### Future Enhancement (out of scope)

Per-user job concurrency limits. E.g., "max 3 running jobs per user." Not needed for initial auth implementation.

---

## 5.10 — End-to-End Flow Summary

```
User A (frontend)
  → Login (gets httpOnly cookies)
  → Navigate to Voice Rx
  → Upload audio file (POST /api/files → user_id set from auth)
  → Create listing (POST /api/listings → user_id set from auth)
  → Run evaluation (POST /api/jobs → user_id set from auth + in params)
  → Poll job status (GET /api/jobs/{id} → scoped by user_id)

Worker (backend)
  → Picks up job from queue
  → Reads user_id from job.user_id / params["user_id"]
  → Resolves User A's LLM settings (from settings table)
  → Creates LLM provider with User A's API key
  → Runs evaluation
  → Writes EvalRun with user_id = User A's ID
  → Updates job status

User A (frontend)
  → Poll sees job completed
  → Fetches eval run (GET /api/eval-runs → scoped by user_id)
  → Sees their results

User B (frontend)
  → Cannot see User A's listings, eval runs, jobs, or settings
  → Has their own LLM keys configured
  → Runs their own evaluations independently
```

---

## Verification Checklist

- [ ] Job rows have `user_id` set from the authenticated user who created them.
- [ ] Worker resolves the submitting user's LLM credentials, not a global key.
- [ ] All result rows (eval_runs, thread_evaluations, etc.) have correct `user_id`.
- [ ] User A cannot cancel User B's jobs.
- [ ] User A cannot see User B's job progress.
- [ ] Stale job recovery still works (server-level, no user scoping).
- [ ] Worker doesn't hold DB sessions open during LLM calls.
- [ ] Service account (Gemini Vertex AI) remains shared across users.
- [ ] Job queue is FIFO across all users.
- [ ] Frontend job polling works without changes (backend scopes the response).
- [ ] Missing LLM credentials for a user result in a clear job failure message, not a crash.
