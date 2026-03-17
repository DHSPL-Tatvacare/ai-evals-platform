# CLAUDE.md

Operational guide for Claude working in this repository. Prefer existing abstractions and patterns.
At session start, read `~/.claude` project memory for context from prior conversations.

## Rule Precedence

1. Direct user instruction
2. This file
3. `.github/copilot-instructions.md`
4. Existing code patterns in touched files

## Architecture Mental Models

1. Frontend is a thin client. All business logic, LLM calls, and persistence run on the backend. Frontend manages UI state and makes API calls.
2. EvalRun is the central entity. Every evaluation outcome is one EvalRun record. `eval_type` determines its shape: `custom`, `full_evaluation`, `human`, `batch_thread`, `batch_adversarial`.
3. Jobs are the execution model. Operations longer than a few seconds run as background jobs: create → poll → get result. Never write custom polling loops in components.
4. Stores are caches. Zustand stores cache server data. PostgreSQL is the source of truth. On page load, stores call their `load*()` methods.
5. The provider abstraction protects runners. Runners never call Gemini/OpenAI/Anthropic SDKs directly. They go through `llm_base.py`, which handles auth, retries, timeouts, and logging.

## Abstractions to Reuse — Never Bypass

- LLM calls → `backend/app/services/evaluators/llm_base.py` providers only. No direct SDK calls from runners.
- Async evaluations → `submitAndPollJob()` from `src/services/api/jobPolling.ts`. No component-level polling loops.
- HTTP → `apiRequest` / `apiUpload` / `apiDownload` from `src/services/api/client.ts`. No raw `fetch` in components.
- Resource data → repository wrappers in `src/services/api/*.ts` and `src/services/storage/`.
- Navigation → route constants from `src/config/routes.ts`. No hardcoded route strings.
- User feedback → `notificationService.success/error/info/warning`. No `alert()`.
- Diagnostics → `logger` / `evaluationLogger`. No `console.log` in production paths.
- CSS merging → `cn()` from `src/utils/cn.ts`.
- UI primitives → `src/components/ui/` before creating new variants.

## Current Registry

- Routers (17): auth, listings, files, prompts, schemas, evaluators, chat, history, settings, tags, jobs, eval_runs, threads, llm, adversarial_config, admin, reports
- ORM tables (19): tenants, users, refresh_tokens, eval_runs, jobs, listings, files, prompts, schemas, evaluators, chat_sessions, chat_messages, history, settings, tags, thread_evaluations, adversarial_evaluations, api_logs, evaluation_analytics
- Zustand stores (15): authStore, appStore, appSettingsStore, llmSettingsStore, globalSettingsStore, listingsStore, schemasStore, promptsStore, evaluatorsStore, chatStore, uiStore, miniPlayerStore, taskQueueStore, jobTrackerStore, crossRunStore
- LLM providers: Gemini (Vertex AI service account + API key), OpenAI, Azure OpenAI, Anthropic
- Job handlers (7): evaluate-voice-rx, evaluate-batch, evaluate-adversarial, evaluate-custom, evaluate-custom-batch, generate-report, generate-cross-run-report
- Active app IDs: `voice-rx`, `kaira-bot`

## Invariants — Do Not Break

- EvalRun `eval_type` polymorphism must be preserved. FK/cascade chain `listings`/`chat_sessions` → `eval_runs` → `thread_evaluations`/`adversarial_evaluations`/`api_logs` must remain intact.
- Voice Rx two-call order is fixed: transcription first (with audio), critique second (text-only `generate_json`). Never send audio on the critique call. Compute statistics server-side from records, not LLM self-reports.
- Job safety: `is_job_cancelled()` checks must exist in all long-running flows. `recover_stale_jobs()` and `recover_stale_eval_runs()` startup paths must remain functional.
- Every data row belongs to a tenant. Every query filters by `tenant_id` from `AuthContext`.
- `SYSTEM_TENANT_ID` and `SYSTEM_USER_ID` are well-known UUIDs for seed data. System prompts/schemas/evaluators are read-only to all tenants.
- `UserMixin` is replaced by `TenantUserMixin`. Both `tenant_id` and `user_id` are required FK references — no defaults.
- LLM settings are per-user-per-tenant, stored at `(tenant_id, user_id, app_id="")`.
- Auth routes (`/api/auth/*`) are the only public routes. All others require Bearer token.
- Gemini on Vertex AI: use `Part.from_bytes()` for media — `client.files.upload()` is not available on Vertex. To disable thinking, omit `thinking_config` entirely — `thinking_budget=0` is rejected. Thinking params differ by model family: 2.5 uses `thinking_budget` (int), 3+ uses `thinking_level` (enum). Do not mix them.
- Do not reintroduce `kaira-evals` as an appId in any frontend store or settings.
- Do not create subdirectory agent rule files (`agents/`, `.cursor/`, etc.). This file is the source of truth for Claude. Creating duplicate rule files in subdirectories is redundant and causes drift.

## Coding Rules — Frontend

- TypeScript strict. Avoid `any`; if unavoidable, localize it.
- Single quotes, semicolons. Match local file style.
- `@/` alias for internal imports. `import type` for type-only imports. External packages before `@/`.
- Named exports for new feature files. Keep existing default exports.
- Zustand in components: select slices — `useStore((s) => s.value)`. Never destructure the full store object.
- Zustand in async callbacks: `useStore.getState()`.
- Explicit interfaces/types for all API payloads and store state.
- Date parsing: explicit `parseDates` at API boundaries, not inline.

## Coding Rules — Backend

- Python internals: snake_case. API JSON: camelCase via `CamelModel`/`CamelORMModel`.
- Schema naming: `XxxCreate`, `XxxUpdate`, `XxxResponse`.
- Routes: async sessions via `Depends(get_db)` and SQLAlchemy `select()`.
- Auth context: `auth: AuthContext = Depends(get_auth_context)` on every route.
- Never use `db.get(Model, id)` for user data — always `select().where()` with tenant/user filters.
- Job params: `tenant_id` and `user_id` are injected by the job submission route. Runners read from params.
- System data: Query with `tenant_id == SYSTEM_TENANT_ID`, not `is_default == True and user_id == "default"`.
- Client errors: `HTTPException` with stable `detail` strings.
- Model changes: update model + schema + `seed_defaults.py` + affected routes together.
- Local Python: `pyenv activate venv-python-ai-evals-arize`. No global installs.

## Anti-Overengineering

- Fix callers passing wrong scope. Do not add fallback chains to lookup functions.
- Do not add new schema fields + frontend sync for UI polish issues when the root bug can be fixed directly.
- Do not add error-surfacing infrastructure when the fix eliminates the error.
- Do not create helpers or abstractions for one-off operations.
- Do not design for hypothetical future requirements. Three similar lines is better than a premature abstraction.

## Common Pitfalls

- Most backend list/get endpoints require `app_id` as a query param. Do not omit it.
- `settings` API: LLM settings scope is `(tenant_id, user_id, app_id="")`. Always pass tenant/user from auth context.
- `listing` source_type rules: do not mix upload and API-flow data.
- Model changes: update model + schema + seed + routes together, or the DB and API go out of sync.

## Build, Run, Lint

```bash
# Full stack
docker compose up --build
docker compose down          # stop, keep DB data
docker compose down -v       # stop, wipe DB volume
docker compose logs -f backend

# Frontend
npm run dev                  # :5173
npm run build
npm run lint
npx tsc -b                   # typecheck only

# Backend (local, without Docker)
pyenv activate venv-python-ai-evals-arize
PYTHONPATH=backend python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8721
```

## References

- Product overview, architecture, data flows: `docs/PROJECT 101.md`
- Full setup (local + Azure): `docs/SETUP.md`
- Agent guide (non-Claude agents): `AGENTS.md`
- Copilot rules: `.github/copilot-instructions.md`
