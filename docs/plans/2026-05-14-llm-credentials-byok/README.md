# LLM Credentials BYOK Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the per-tenant×per-user LLM settings blob with a per-tenant encrypted `tenant_llm_providers` table, a single credential resolver, an admin control plane, and a slim wizard component — remove tenant LLM env fallbacks, and move client-side LLM calls server-side.

**Architecture:** BYOK only. Credentials live in one encrypted Postgres table keyed `(tenant_id, provider)`. A single `resolve_llm_credentials(db, tenant_id, provider)` returns credentials; callers supply provider+model from their own entity or job params. No `user_id`, no `auth_intent`, no `provider_override`, no env-var fallback for real tenants. The Gemini service account survives for the system tenant only. Sherlock requires an OpenAI-family provider. Client-side LLM calls (prompt/schema generation, structured extraction) move to backend endpoints — the encrypted key never reaches the browser.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async / Alembic / Fernet / React 19 / TypeScript / Zustand / TanStack Query / Vite.

**Design spec:** `tatvacare-obsidian/Projects/ai-evals-platform/Designs/llm-credentials-byok-redesign.md`

**Platform-plan boundary:** This BYOK plan is self-contained. Do **not** depend on `docs/plans/platform/phase-15-tanstack-query-migration.md` or Phase 16 codegen work; those platform plans are deferred. This plan owns the complete `llmSettingsStore` removal, every live consumer migration, the admin AI Settings query surface, and the legacy `llm-settings` row retirement. If Platform Phase 15 resumes later, its `llmSettingsStore` wave must be skipped or re-audited after this BYOK branch lands.

---

## Phases

Three phases. **All three are implemented on a single shared branch — `feat/llm-credentials-cleanup`.** Phase 1 creates the branch off `main`; Phases 2 and 3 continue on the same branch. Every task commits to this branch. There are NO per-phase branches and NO mid-project merges to `main` — the whole feature is reviewed and merged as one branch at the end. Each phase still leaves the application in a working, shippable state at its last commit, so the branch is always in a coherent state between phases.

| Phase | Status | File | What it delivers |
|---|---|---|---|
| 1 | ✅ **COMPLETE** (2026-05-16, branch head `9252a76`) | [phase-1-backend-foundation.md](phase-1-backend-foundation.md) | New table + migration 0047 (create + backfill; **old `application_settings` rows kept**) + Fernet crypto + `LLM_CREDENTIAL_KEY` boot guard + `resolve_llm_credentials` + delete `settings_helper.py` + rewire all 13 live backend call sites + Sherlock + submission-site provider/model injection + remove tenant credential env fallbacks + deploy config. Plus **one bridging frontend edit** (`CreateEvaluatorWizard.tsx`) so the evaluator-draft flow keeps working. Old `llmSettingsStore` keeps functioning untouched until Phase 3. |
| 2 | ⏳ Ready to start | [phase-2-admin-control-plane.md](phase-2-admin-control-plane.md) | `/api/admin/ai-settings/*` routes (list/upsert/discover/validate) + 3 server-side LLM-assist endpoints + `routes/llm.py` `auth-status` rewrite + `AdminAISettingsPage` UI + TanStack wiring. |
| 3 | ⏳ Pending | [phase-3-frontend-cleanup.md](phase-3-frontend-cleanup.md) | Slim two-row `LLMConfigSection` + rewire every live `llmSettingsStore`/legacy LLM consumer + fix `EvaluationOverlay` + rewire the 7 client-side LLM-assist surfaces to the new endpoints + delete all of `src/services/llm/` + delete `llmSettingsStore` + remove `ProviderConfigCard` + update guide references + asset-policy change + migration 0048 (drop old rows — the final cleanup, giving a full rollback window). |

**Branch discipline:** do not start Phase N+1 until Phase N's "Verification Checklist" is fully green and committed on `feat/llm-credentials-cleanup`. Because there is no per-phase merge gate, this self-discipline is the only thing keeping the branch coherent.

---

## Phase 1 → Phase 2 handoff brief

Read this section before starting Phase 2. It captures what changed in Phase 1, the contracts Phase 2 inherits, and the deviations from the original plan that Phase 2 must take as-is.

### Branch state at start of Phase 2

- **Branch:** `feat/llm-credentials-cleanup` (do **not** create a new branch — Phase 2 commits go here)
- **HEAD:** `9252a76 fix(llm-byok): post-audit cleanups (server_default + docs + dev compose)` — 14 commits ahead of `main`
- **Working tree:** clean
- **Alembic head:** `0047` (next revision = `0048`, owned by Phase 3)

### Hard prerequisites Phase 2 inherits

1. `LLM_CREDENTIAL_KEY` is now **required** on every runtime (local, CI, prod). Generate with:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   On Azure Container Apps, set as a secret (never `value:`) and reference via `secretref:`. Boot validator raises `RuntimeError` if missing or invalid Fernet.
2. `platform.tenant_llm_providers` table is live. Backfilled from the most-recent `application_settings.llm-settings` row per tenant. Old rows are **still present** (deleted by migration 0048 in Phase 3).
3. The Gemini service-account fallback survives, but **only for `SYSTEM_TENANT_ID`** — real-tenant Gemini fails fast with `ProviderNotConfiguredError` if no row.

### Public surface Phase 2 builds on

```python
from app.services.llm_credentials import (
    resolve_llm_credentials,      # async (db, tenant_id, provider) -> ResolvedCredentials
    ResolvedCredentials,          # frozen dataclass — fields below
    ProviderNotConfiguredError,   # raised when no usable credential
    invalidate_cache,             # call after admin writes
)
from app.models.tenant_llm_provider import TenantLlmProvider
```

`ResolvedCredentials` fields: `provider, api_key, base_url, extra_config, service_account_path`. **The resolver does not return a model name** — Phase 2 admin write/read paths and Phase 3 callers always pair credentials with an explicit model from the caller's own entity.

`ResolvedCredentials` is cached for 60s per `(tenant_id, provider)`. **Phase 2's upsert/delete endpoints MUST call `invalidate_cache(tenant_id, provider)` after every write** or operators will see 60s of stale behavior after enabling/disabling a provider. This is non-negotiable.

### Sherlock contract changes (Phase 2 narrative must reflect these)

- `get_sherlock_azure_client(*, tenant_id)` — `user_id` is gone. The plan's Task 7 dropped it.
- Sherlock is **provider-flexible** within the OpenAI family: it tries `azure_openai` first, falls back to `openai`. Both expose the Responses API.
- Specialist + supervisor function signatures widened from `openai.AsyncAzureOpenAI` → `openai.AsyncOpenAI` in:
  - `backend/app/services/sherlock_v3/supervisor.py:182`
  - `backend/app/services/sherlock_v3/query_synthesis_specialist.py:125`
  - `backend/app/services/sherlock_v3/data_specialist.py:1065`
  - `backend/app/services/sherlock_v3/authoring_specialist.py:285`

  Phase 2's `auth-status` rewrite must keep this surface — do not narrow back to `AsyncAzureOpenAI`.

### Submission-site contracts (Phase 2 admin UI must respect these)

- `generate-evaluator-draft` job **requires** `params["provider"]` and `params["model"]`. The handler at `backend/app/services/job_worker.py:1533-1537` raises `ValueError` if either is missing.
- `backfill-lead-signals` job **requires** `params["provider"]` and `params["model"]`. `parse_request` raises `ValueError`. The admin endpoint at `backend/app/routes/analytics_admin.py:582` validates these via `BackfillLeadSignalsRequest`.
- The wizard fix at `src/features/evals/components/CreateEvaluatorWizard.tsx:361-367` currently reads `provider` from `useLLMSettingsStore.getState()`. **This is the one bridging edit Phase 1 was allowed.** Phase 3 replaces it with a TanStack query against the new AI Settings surface.

### Plan-vs-reality deltas Phase 2 should know about

1. **Call-site count: 13 live, not 14.** The plan listed 14 `get_llm_settings_from_db` call sites including `inside_sales_runner.py`. That file was already removed before this branch started (consolidated into `eval_runner_shell.py`). Net live rewires: 13. No design impact.
2. **`auth-status` is half-rewritten.** Task 12 had to remove tenant env-var reads from `auth_status` to keep the route booting; it now queries `tenant_llm_providers` directly. Phase 2's Task that "rewrites auth-status" should treat it as already converted to query the table — Phase 2 work is the broader `routes/llm.py` discovery extraction (`llm_model_discovery.py`), not re-implementing `auth_status`.
3. **`_create_logging_llm` signature change.** `backend/app/services/reports/report_generation_service.py:166` now takes `db: AsyncSession`, `run_provider: str | None`, `run_model: str | None`. Both callers updated. Phase 2 has no work here; Phase 3 doesn't touch it either.
4. **`generate_evaluator_draft` signature change.** `backend/app/services/evaluators/evaluator_draft_service.py:27` now takes required `provider: str, model: str`. Local variable rename: `provider` → `llm_client` for the wrapped LLM (to free up `provider` for the parameter). The internal `inner` variable is now wrapped, then assigned to `llm_client`. Don't accidentally collide with the parameter name when extending this function.
5. **Test-environment caveat.** The `db_session` fixture in `backend/tests/conftest.py` uses outer-transaction-plus-savepoint isolation — rows committed in a test are **not** visible to other connections. Code paths that open their own `async with async_session() as db:` must mock the session factory in tests. See the `_patch_async_session` fixture in `backend/tests/test_sherlock_azure_client.py` for the pattern. Phase 2's admin route tests will hit this — the routes will use `Depends(get_db)`, so they share the test session, but any boot-time code paths or background tasks that open their own session need the same patch.
6. **`is_enabled` has `server_default=false()`.** Both the migration and the model declare it. Phase 2's admin upsert must explicitly set `is_enabled=True` to enable a provider; rows default to disabled on insert.

### Files that **do not exist yet** (Phase 2 creates them)

- `backend/app/routes/admin_ai_settings.py`
- `backend/app/routes/llm_assist.py`
- `backend/app/schemas/ai_settings.py`
- `backend/app/schemas/llm_assist.py`
- `backend/app/services/llm_model_discovery.py`
- `backend/app/services/llm_assist_service.py`
- `src/features/admin/pages/AdminAISettingsPage.tsx` + sub-components
- `src/services/api/aiSettingsApi.ts`
- `src/services/api/aiSettingsQueries.ts`

### Files Phase 2 must NOT touch

- `src/stores/llmSettingsStore.ts` — deleted in Phase 3, not Phase 2
- `src/components/ui/LLMConfigSection.tsx` — rewritten in Phase 3, not Phase 2
- `src/services/llm/*` — deleted in Phase 3
- `backend/alembic/versions/0048_*` — Phase 3 owns the row-deletion migration
- `platform.application_settings` `llm-settings` rows — preserved through Phase 2 for rollback safety
- `backend/app/services/asset_policy.py` `llm-settings` entry — Phase 3 retires it
- `backend/entrypoint.sh` SA decode block — untouched indefinitely
- Sherlock specialist client annotations (already widened to `AsyncOpenAI`)

### Verification gates Phase 2 inherits as clean

These should still be clean when Phase 2 starts. If any fails, stop and investigate before adding new work:

```bash
rg "get_llm_settings_from_db|settings_helper" backend/                # → 0 hits
rg "GEMINI_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|AZURE_OPENAI_API_KEY|DEFAULT_LLM_PROVIDER|EVAL_TEMPERATURE" backend/app/   # → 0 hits
rg "GEMINI_SERVICE_ACCOUNT_PATH" backend/app/                          # → 3 hits (config.py, resolver.py, routes/llm.py auth_status)
```

### Phase 1 commit log (for reference)

```
9252a76 fix(llm-byok): post-audit cleanups (server_default + docs + dev compose)
d515de1 chore(llm-byok): deploy config cleanup + registry updates
10bcc6d feat(llm-byok): remove tenant LLM env fallbacks
7f10437 feat(llm-byok): delete settings_helper.py — superseded by resolve_llm_credentials
49f675e feat(llm-byok): rewire routes/llm.py call sites to resolve_llm_credentials
568df2f feat(llm-byok): submission sites inject provider/model into job params
cb5686a feat(llm-byok): rewire evaluator/report/job call sites to resolve_llm_credentials
8107ba6 feat(llm-byok): Sherlock resolves credentials via tenant_llm_providers
e0c39e5 feat(llm-byok): resolve_llm_credentials resolver + cache
351e2e1 feat(llm-byok): migration 0047 — tenant_llm_providers + backfill
92b9527 feat(llm-byok): TenantLlmProvider ORM model
2e69df5 feat(llm-byok): boot-validate LLM_CREDENTIAL_KEY
3e3caf5 feat(llm-byok): Fernet crypto module for LLM credentials
eca72d6 feat(llm-byok): add LLM_CREDENTIAL_KEY config field
```

---

## Master change-site inventory

Verified by exhaustive code sweep. Every site below is touched by some phase.

### Backend — `get_llm_settings_from_db` call sites (14, all rewired in Phase 1)
1. `backend/app/routes/llm.py:105-109` — `provider_override="azure_openai"` — in helper `_discover_azure_openai_models` (no `db` in scope → open `async_session()`)
2. `backend/app/routes/llm.py:235-239` — `provider_override="gemini"` — in helper `_discover_gemini_models` (open `async_session()`)
3. `backend/app/routes/llm.py:315-319` — `provider_override=provider` — in helper `_get_provider_key_from_db` (open `async_session()`)
4. `backend/app/services/sherlock_v3/azure_client.py:39-44` — hardcoded `provider_override='azure_openai'`
5. `backend/app/services/evaluators/batch_runner.py:188,190-193` — `provider` from `params` (open `async_session()`)
6. `backend/app/services/evaluators/evaluator_draft_service.py:45,54-58` — **GAP: provider/model only from settings** — fixed in Phase 1 Task 8 (read `params["provider"]/["model"]`); open `async_session()`
7. `backend/app/services/evaluators/inside_sales_runner.py:37,373-378` — `provider` from `llm_config` (open `async_session()`)
8. `backend/app/services/evaluators/voice_rx_runner.py:212-216` — `provider` from `params` (open `async_session()`)
9. `backend/app/services/evaluators/adversarial_runner.py:456-460` — `provider` from `llm_provider` local (open `async_session()`)
10. `backend/app/services/evaluators/custom_evaluator_runner.py:259-263` — `provider` from `params` (open `async_session()`)
11. `backend/app/services/analytics/backfill_lead_signals_job.py:511-517` — **GAP: provider/model only from settings** — fixed in Phase 1 Task 8 (read `params["provider"]/["model"]`); open `async_session()`
12. `backend/app/services/reports/base_report_service.py:17,116-120` — provider/model on `run.llm_provider`/`run.llm_model`; **uses `self.db`**
13. `backend/app/services/reports/report_generation_service.py:37,175-178` — provider/model on `report_run` row; **needs `db` threaded from caller at `:450`**
14. `backend/app/services/evaluators/eval_runner_shell.py:298-306` — provider/model on `params.llm_config`; open `async_session()` or reuse a session in scope; required before `settings_helper.py` can be deleted.

### Backend — Sherlock caller (Phase 1)
- `backend/app/services/sherlock_v3/runtime.py:421-422` — the only caller of `get_sherlock_azure_client`; currently passes `tenant_id`+`user_id` → drop `user_id`.

### Backend — job submission sites (Phase 1 Task 9)
- `backend/app/routes/analytics_admin.py:593-605,649-663` — `backfill-lead-signals` submitter — add `provider`/`model` to request body + params dict.
- `src/features/*/components/CreateEvaluatorWizard.tsx:~361` — `generate-evaluator-draft` submitter — add `provider`/`model` to the `submitAndPollJob` params (the wizard already holds `modelId` state at `:119`). **This is the one bridging frontend edit in Phase 1.**
- `backend/app/routes/jobs.py:89-126` — generic job submission; pass-through — confirm `provider`/`model` survive into `params` (no special handling needed, but verify).

### Backend — other (Phase 1 unless noted)
- `backend/app/services/evaluators/settings_helper.py` — **deleted** (Phase 1)
- `backend/app/config.py:19-33` — remove tenant credential/model fallback fields that no runtime code reads after rewiring; add `LLM_CREDENTIAL_KEY` (Phase 1). Keep `GEMINI_SERVICE_ACCOUNT_PATH` and the production `GEMINI_SERVICE_ACCOUNT_JSON` entrypoint path for the system-tenant Gemini service-account fallback until a later SA-removal project.
- `backend/app/main.py:39-77` — `_validate_startup_config` gains `LLM_CREDENTIAL_KEY` check (Phase 1)
- `backend/app/routes/chat_engine.py:13-20` — drop `os.getenv("OPENAI_MODEL")` (Phase 1)
- `backend/app/routes/llm.py` — `auth-status` rewritten + discovery extracted to `llm_model_discovery.py` (Phase 2); the old `/discover-models` + `/models` routes deleted (Phase 3, when `modelDiscovery.ts` goes)
- `backend/app/services/asset_policy.py:19` — remove `llm-settings` from `private_only_keys` (**Phase 3**, with the row deletion)
- `backend/app/models/__init__.py` — register `TenantLlmProvider` (Phase 1)

### Backend — new files
- `backend/app/services/llm_credentials/{__init__,crypto,resolver}.py` (Phase 1)
- `backend/app/models/tenant_llm_provider.py` (Phase 1)
- `backend/alembic/versions/0047_tenant_llm_providers.py` (Phase 1), `0048_drop_llm_settings_rows.py` (Phase 3). Current repo already owns `0045_*` and `0046_*`; do not reuse those revision IDs.
- `backend/app/routes/admin_ai_settings.py`, `backend/app/routes/llm_assist.py`, `backend/app/schemas/ai_settings.py`, `backend/app/schemas/llm_assist.py`, `backend/app/services/llm_model_discovery.py`, `backend/app/services/llm_assist_service.py` (Phase 2)

### Backend — deploy config (Phase 1)
- `docker-compose.prod.yml:46-61`, `docker-compose.yml`, `.env.backend` example, `docs/SETUP.md`, `docs/devops-handover.md`. `backend/entrypoint.sh` SA block **untouched**.
- **Hard deploy prerequisite:** set `LLM_CREDENTIAL_KEY` in every runtime environment **before** deploying the image that runs migration 0047. `backend/entrypoint.sh` runs `alembic upgrade head` before the app starts; migration 0047 backfills encrypted rows and will fail if the key is missing or invalid.

### Backend — tests
- Phase 1: `test_inside_sales_runner_unittest.py:153`, `test_cost_tracking_phase3_unittest.py:50,94`
- Phase 3: `test_settings_routes.py:74-75,138-142,171`, `test_apps_routes.py:53,137`, `test_rule_catalog_routes.py:41` (with the asset-policy change)

### Frontend — Phase 3 unless noted
- `src/components/ui/LLMConfigSection.tsx` — rewritten (Phase 3). Current props: `provider, onProviderChange, model, onModelChange, showThinking, thinking, onThinkingChange, compact, dropdownDirection, onModelsLoading` — **removed:** `showThinking, thinking, onThinkingChange, onModelsLoading`.
- `src/stores/llmSettingsStore.ts` — **deleted** only after the grep gate is clean (Phase 3)
- `src/stores/index.ts:1`, `src/app/Providers.tsx:7`, `src/stores/authStore.ts:7` — drop `llmSettingsStore` export/load/reset (Phase 3). `authStore.logout` must evict the admin AI Settings query cache through the existing query client if one is available; do not leave a stale credential cache after logout.
- `src/features/chat-widget/ChatWidget.tsx:20` — replace `useLLMSettingsStore`/`hasProviderCredentials` with `useProviderConfigs` and OpenAI-family availability (Phase 3)
- Live legacy LLM/store consumers to migrate in Phase 3 before deletion: `src/features/quickActions/registry.ts`, `src/features/evals/components/AIEvalRequest.tsx`, `src/features/evals/hooks/useEvaluatorRunner.ts`, `src/features/evals/hooks/useAIEvaluation.ts`, `src/features/evalRuns/components/NewBatchEvalOverlay.tsx`, `src/features/evalRuns/components/NewAdversarialOverlay.tsx`, `src/features/settings/hooks/useSettingsForm.ts`, plus every file returned by `rg "llmSettingsStore|useLLMSettingsStore|hasLLMCredentials|getProviderApiKey|hasProviderCredentials|LLM_PROVIDERS" src`.
- 6 primary `LLMConfigSection` consumers: `RunAllOverlay.tsx:3,129`, `EvaluationOverlay.tsx:20,31,465,502,518,534`, `LLMConfigStep.tsx:4,99,119`, `IssuesTab.tsx:11,151`, `ReportTab.tsx:4,728`, `PlatformReportRenderer.tsx:26,1180` (Phase 3)
- 3 `ProviderConfigCard` consumers: `VoiceRxSettingsPage.tsx:8,110`, `KairaBotSettingsPage.tsx:8,111`, `InsideSalesSettings.tsx:8,80` (Phase 3); `ProviderConfigCard.tsx` deleted (Phase 3)
- **7 client-side LLM-assist surfaces** (rewired to backend endpoints, Phase 3): `PromptGeneratorModal.tsx`, `SchemaGeneratorModal.tsx`, `SchemaGeneratorInline.tsx`, `useStructuredExtraction.ts`, `schemaService.ts`, `StructuredOutputsView.tsx`, `ExtractionModal.tsx`
- **`src/services/llm/` — entire directory deleted** (Phase 3): `pipeline/*`, `GeminiProvider.ts`, `providerRegistry.ts`, `modelDiscovery.ts`, `retryPolicy.ts`, `index.ts` (verified: `providerRegistry`/`GeminiProvider` already dead; the rest die once the 7 surfaces are rewired)
- `src/features/settings/components/ModelSelector.tsx` — **deleted** (Phase 3 after `rg "ModelSelector" src` is clean)
- `src/config/routes.ts` — add admin AI settings route (Phase 2)
- `src/features/admin/pages/AdminAISettingsPage.tsx` + sub-components (Phase 2)
- `src/services/api/aiSettingsApi.ts` + `src/services/api/aiSettingsQueries.ts` (Phase 2 — temporary accepted exception while platform query migration is deferred: hooks live in `services/api/` so shared `components/ui/LLMConfigSection` can import them without a `ui → features` layering violation. Revisit only when Platform Phase 15 resumes.)
- `src/services/api/llmAssistApi.ts` (Phase 3 — client for the 3 assist endpoints)

### Preserved — do NOT touch
- `settingsRepository` (`src/services/api/settingsApi.ts`) and `/api/settings` — shared infra for `api-credentials`, `adversarial-config`, `credential-pool-groups`. Only the `llm-settings` key is retired (Phase 3).
- `backend/entrypoint.sh` SA decode block.
- `llm_base.py` provider wrappers — they still receive `api_key` + `model_name`.
- `ORCHESTRATION_CONNECTION_KEY`, `ANALYTICS_DATABASE_URL`.
- `GEMINI_SERVICE_ACCOUNT_PATH` / production `GEMINI_SERVICE_ACCOUNT_JSON` decode path — system tenant only in the new resolver.

`EVAL_TEMPERATURE` is removed only if the implementation-time grep still proves zero live consumers. Do not remove env fields by category; remove only fields that are no longer read after the backend rewiring.

## Conventions

- TDD: failing test → run → implement → run → commit. Every task ends in a commit.
- Backend tests: `pyenv activate venv-python-ai-evals-arize && PYTHONPATH=backend python -m pytest backend/tests/<file> -v`
- Frontend checks: `npm run lint && npx tsc -b`
- Raw SQL in migrations MUST schema-qualify (`platform.tenant_llm_providers`).
- The resolver opens no session; sites without a `db` in scope open a throwaway `async with async_session() as db:` — it does one SELECT, this is cheap and correct.
- No fallbacks, no overrides, no legacy shims. Dead code is deleted, not commented out.
- Frontend request bodies passed to `apiRequest` MUST be `JSON.stringify(...)`; this repo's `apiRequest` sets JSON headers but does not stringify object bodies.
- Azure OpenAI rewires MUST translate resolved credentials into the existing provider factory shape: `azure_endpoint=creds.base_url or ""` and `api_version=creds.extra_config.get("api_version", "2025-03-01-preview")`.
- Final grep gates distinguish live code from documentation. Live code must be clean; guide/docs references are either updated deliberately in Phase 3 or excluded explicitly with a comment explaining why.
