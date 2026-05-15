# Phase 2 — Admin Control Plane + Server-Side Assist

> **Status: ⏳ READY TO START.** Phase 1 is complete on `feat/llm-credentials-cleanup` at `9252a76`. **Continue on this same branch — do NOT create a new branch.** Before writing any code, read the [Phase 1 → Phase 2 handoff brief in README.md](README.md#phase-1--phase-2-handoff-brief): it lists inherited contracts (`resolve_llm_credentials`, `ResolvedCredentials`, `ProviderNotConfiguredError`, `invalidate_cache`), Sherlock signature changes you must preserve, the `auth-status` already partially rewired in Phase 1, and the deltas where this plan differs from what actually shipped.

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. For React work, follow `frontend-design` conventions and the repo Design System Rules in `CLAUDE.md`.

**Goal:** Ship the `/api/admin/ai-settings/*` routes (list/upsert/discover-models/validate), the 3 server-side LLM-assist endpoints (replacing client-side prompt/schema/extraction calls), rewrite `routes/llm.py` `auth-status`, and build the **Admin → AI Settings** page.

**Architecture:** New admin sub-router gated by `configuration:edit`. GET redacts `api_key`; PUT preserves a blank key. The 3 assist endpoints run prompt/schema generation + structured extraction server-side via `resolve_llm_credentials` — the encrypted key never reaches the browser. Frontend page matches the approved reference exactly. Server data flows through TanStack Query via `apiQueryFn`.

**Branch:** Continue on `feat/llm-credentials-cleanup` — the branch Phase 1 created. Confirm you are on it (`git branch --show-current`) before touching anything, and that Phase 1 is fully committed here. Commit every task on this branch. Do NOT merge to `main` and do NOT create a new branch.

**Depends on:** Phase 1 (`tenant_llm_providers`, `resolve_llm_credentials`, `invalidate_cache`, crypto).

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/schemas/ai_settings.py` | `CamelModel` schemas for admin AI settings (redacted-key responses). |
| `backend/app/schemas/llm_assist.py` | `CamelModel` schemas for the 3 assist endpoints. |
| `backend/app/routes/admin_ai_settings.py` | `/api/admin/ai-settings/*`: list, upsert, discover-models, validate. |
| `backend/app/routes/llm_assist.py` | `/api/llm/assist/*`: generate-prompt, generate-schema, extract-structured. |
| `backend/app/services/llm_model_discovery.py` | `list_models_for_provider(provider, creds)` — extracted from `routes/llm.py`. |
| `backend/app/services/llm_assist_service.py` | The prompt/schema/extraction logic, server-side, via `llm_base.py`. |
| `backend/app/routes/llm.py` | `auth-status` rewritten around `tenant_llm_providers`. |
| `src/services/api/aiSettingsApi.ts` | Typed client for the admin AI settings endpoints. |
| `src/services/api/aiSettingsQueries.ts` | TanStack hooks. **Temporary accepted exception:** hooks live in `services/api/` while Platform Phase 15 is deferred, so shared `components/ui/LLMConfigSection` can import them without a `ui → features` layering violation. Re-audit this location only when the platform query migration resumes. |
| `src/features/admin/pages/AdminAISettingsPage.tsx` + `components/aiSettings/*` | The admin page. |
| `src/config/routes.ts` | Admin AI settings route. |

---

## Task 1: AI settings + assist schemas

**Files:** Create `backend/app/schemas/ai_settings.py`, `backend/app/schemas/llm_assist.py`. Test `backend/tests/test_ai_settings_schemas.py`.

Supported providers are fixed: `openai`, `azure_openai`, `anthropic`, `gemini`.

- [ ] **Step 1: Write the failing test.**

```python
# backend/tests/test_ai_settings_schemas.py
def test_provider_response_redacts_key():
    from app.schemas.ai_settings import ProviderConfigResponse
    r = ProviderConfigResponse(
        provider="openai", is_enabled=True, has_api_key=True, base_url=None,
        extra_config={}, curated_models=["gpt-5.4"], validation_status="ok",
        last_validated_at=None)
    dumped = r.model_dump()
    assert "api_key" not in dumped and "api_key_encrypted" not in dumped
    assert dumped["hasApiKey"] is True


def test_upsert_request_allows_blank_key():
    from app.schemas.ai_settings import ProviderConfigUpsert
    body = ProviderConfigUpsert(is_enabled=True, api_key="", base_url=None,
                                extra_config={}, curated_models=[])
    assert body.api_key == ""
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Write `ai_settings.py`.** Follow the repo's `CamelModel` base (check `backend/app/schemas/`).

```python
# backend/app/schemas/ai_settings.py
"""Schemas for /api/admin/ai-settings. Responses NEVER carry the API key —
only has_api_key: bool. Upserts treat a blank api_key as "preserve stored secret"."""
from __future__ import annotations
from datetime import datetime
from app.schemas.base import CamelModel  # adjust to the repo's CamelModel location

SUPPORTED_PROVIDERS = ("openai", "azure_openai", "anthropic", "gemini")


class ProviderConfigResponse(CamelModel):
    provider: str
    is_enabled: bool
    has_api_key: bool
    base_url: str | None
    extra_config: dict
    curated_models: list[str]
    validation_status: str
    last_validated_at: datetime | None


class ProviderConfigUpsert(CamelModel):
    is_enabled: bool
    api_key: str = ""          # blank => preserve stored key
    base_url: str | None = None
    extra_config: dict = {}
    curated_models: list[str] = []


class ModelSearchRequest(CamelModel):
    search: str = ""


class ModelSearchResponse(CamelModel):
    models: list[str]


class ValidateResponse(CamelModel):
    validation_status: str     # 'ok' | 'invalid'
    detail: str | None = None
```

- [ ] **Step 4: Write `llm_assist.py`.**

```python
# backend/app/schemas/llm_assist.py
"""Schemas for /api/llm/assist/* — server-side prompt/schema generation + extraction.
Every request carries an explicit provider + model (BYOK — no defaults)."""
from __future__ import annotations
from typing import Literal
from app.schemas.base import CamelModel

PromptType = Literal["transcription", "evaluation", "extraction"]


class GeneratePromptRequest(CamelModel):
    provider: str
    model: str
    prompt_type: PromptType
    user_idea: str


class GeneratePromptResponse(CamelModel):
    prompt: str


class GenerateSchemaRequest(CamelModel):
    provider: str
    model: str
    prompt_type: PromptType
    user_idea: str


class GenerateSchemaResponse(CamelModel):
    schema: dict


class ExtractStructuredRequest(CamelModel):
    provider: str
    model: str
    prompt: str
    prompt_type: Literal["freeform", "schema"]
    input_source: Literal["transcript", "audio", "both"]
    transcript: str | None = None
    audio_base64: str | None = None
    audio_mime_type: str | None = None


class ExtractStructuredResponse(CamelModel):
    result: dict
    status: Literal["completed", "failed"]
    error: str | None = None
```

- [ ] **Step 5: Run → PASS.**

- [ ] **Step 6: Commit.** `git add backend/app/schemas/ai_settings.py backend/app/schemas/llm_assist.py backend/tests/test_ai_settings_schemas.py && git commit -m "feat(llm-byok): AI settings + LLM-assist schemas"`

---

## Task 2: `/api/admin/ai-settings` — list + upsert

**Files:** Create `backend/app/routes/admin_ai_settings.py`; register the router. Test `backend/tests/test_admin_ai_settings_routes.py`.

**Contract:**
- `GET /api/admin/ai-settings/providers` → all 4 providers (missing rows come back `is_enabled=false, has_api_key=false, validation_status="untested"`).
- `PUT /api/admin/ai-settings/providers/{provider}` → upsert; blank `api_key` preserves the stored ciphertext; on success calls `invalidate_cache(tenant_id, provider)`.
- Both `require_permission('configuration:edit')`, tenant-scoped via `auth.tenant_id`.

- [ ] **Step 1: Write the failing test.**

```python
# backend/tests/test_admin_ai_settings_routes.py
import pytest


@pytest.mark.asyncio
async def test_list_returns_all_four_providers(admin_client):
    resp = await admin_client.get("/api/admin/ai-settings/providers")
    assert resp.status_code == 200
    assert {p["provider"] for p in resp.json()} == {"openai", "azure_openai", "anthropic", "gemini"}


@pytest.mark.asyncio
async def test_upsert_stores_encrypted_key_and_redacts_response(admin_client, db_session):
    resp = await admin_client.put("/api/admin/ai-settings/providers/openai", json={
        "isEnabled": True, "apiKey": "sk-secret-123", "baseUrl": None,
        "extraConfig": {}, "curatedModels": ["gpt-5.4"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["hasApiKey"] is True and "apiKey" not in body
    from app.models.tenant_llm_provider import TenantLlmProvider
    from sqlalchemy import select
    row = (await db_session.execute(
        select(TenantLlmProvider).where(TenantLlmProvider.provider == "openai"))).scalar_one()
    assert row.api_key_encrypted and "sk-secret-123" not in row.api_key_encrypted


@pytest.mark.asyncio
async def test_blank_key_preserves_stored_secret(admin_client):
    await admin_client.put("/api/admin/ai-settings/providers/openai", json={
        "isEnabled": True, "apiKey": "sk-first", "baseUrl": None,
        "extraConfig": {}, "curatedModels": []})
    resp = await admin_client.put("/api/admin/ai-settings/providers/openai", json={
        "isEnabled": True, "apiKey": "", "baseUrl": None,
        "extraConfig": {}, "curatedModels": ["gpt-5.4"]})
    assert resp.json()["hasApiKey"] is True


@pytest.mark.asyncio
async def test_upsert_requires_configuration_edit(client_without_permission):
    resp = await client_without_permission.put("/api/admin/ai-settings/providers/openai", json={
        "isEnabled": True, "apiKey": "x", "baseUrl": None,
        "extraConfig": {}, "curatedModels": []})
    assert resp.status_code == 403
```

> Fixtures `admin_client`, `client_without_permission`, `db_session`: reuse the repo's auth-test fixtures from `conftest.py`. If a "client with a specific permission" fixture doesn't exist, copy the pattern from the cost-admin route tests (cost-admin also uses `require_permission`).

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Write the router.** Copy import paths (`AuthContext`, `require_permission`, `get_db`) from `backend/app/routes/cost.py`.

```python
# backend/app/routes/admin_ai_settings.py
"""Admin control plane for per-tenant LLM provider credentials.
Gated by configuration:edit, scoped to the caller's tenant. GET redacts keys;
PUT preserves a blank key. Mirrors the cost-admin sub-router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthContext, require_permission
from app.database import get_db
from app.models.tenant_llm_provider import TenantLlmProvider
from app.schemas.ai_settings import (
    SUPPORTED_PROVIDERS, ProviderConfigResponse, ProviderConfigUpsert)
from app.services.llm_credentials import invalidate_cache
from app.services.llm_credentials.crypto import encrypt_secret

router = APIRouter(prefix="/api/admin/ai-settings", tags=["admin-ai-settings"])


def _to_response(provider: str, row: TenantLlmProvider | None) -> ProviderConfigResponse:
    if row is None:
        return ProviderConfigResponse(
            provider=provider, is_enabled=False, has_api_key=False, base_url=None,
            extra_config={}, curated_models=[], validation_status="untested",
            last_validated_at=None)
    return ProviderConfigResponse(
        provider=provider, is_enabled=row.is_enabled,
        has_api_key=bool(row.api_key_encrypted), base_url=row.base_url,
        extra_config=dict(row.extra_config or {}),
        curated_models=list(row.curated_models or []),
        validation_status=row.validation_status, last_validated_at=row.last_validated_at)


@router.get("/providers", response_model=list[ProviderConfigResponse])
async def list_providers(
    auth: AuthContext = require_permission("configuration:edit"),
    db: AsyncSession = Depends(get_db),
):
    rows = {r.provider: r for r in (await db.execute(
        select(TenantLlmProvider).where(TenantLlmProvider.tenant_id == auth.tenant_id)
    )).scalars()}
    return [_to_response(p, rows.get(p)) for p in SUPPORTED_PROVIDERS]


@router.put("/providers/{provider}", response_model=ProviderConfigResponse)
async def upsert_provider(
    body: ProviderConfigUpsert,
    provider: str = Path(...),
    auth: AuthContext = require_permission("configuration:edit"),
    db: AsyncSession = Depends(get_db),
):
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    row = (await db.execute(select(TenantLlmProvider).where(
        TenantLlmProvider.tenant_id == auth.tenant_id,
        TenantLlmProvider.provider == provider))).scalar_one_or_none()
    if row is None:
        row = TenantLlmProvider(tenant_id=auth.tenant_id, provider=provider)
        db.add(row)
    row.is_enabled = body.is_enabled
    row.base_url = body.base_url
    row.extra_config = body.extra_config
    row.curated_models = body.curated_models
    row.updated_by = auth.user_id
    if body.api_key:  # blank => preserve stored ciphertext
        row.api_key_encrypted = encrypt_secret(body.api_key)
        row.validation_status = "untested"  # new key must be re-validated
    await db.commit()
    await db.refresh(row)
    invalidate_cache(auth.tenant_id, provider)
    return _to_response(provider, row)
```

- [ ] **Step 4: Register the router** next to the other `include_router` calls. Update `CLAUDE.md` "Route groups" count + list (add `admin_ai_settings`).

- [ ] **Step 5: Run → PASS.**

- [ ] **Step 6: Commit.** `git add backend/app/routes/admin_ai_settings.py backend/tests/test_admin_ai_settings_routes.py CLAUDE.md && git commit -m "feat(llm-byok): admin AI settings list + upsert routes"`

---

## Task 3: discover-models + validate routes (+ extract `llm_model_discovery`)

**Files:** Create `backend/app/services/llm_model_discovery.py`; modify `backend/app/routes/admin_ai_settings.py`, `backend/app/routes/llm.py` (extraction). Extend `backend/tests/test_admin_ai_settings_routes.py`.

- [ ] **Step 1: Extract `llm_model_discovery.py`.** Move the per-provider model-listing bodies out of `routes/llm.py` (`_discover_azure_openai_models`, `_discover_gemini_models`, `_discover_openai_models`, `_discover_anthropic_models`) into one entry point:
```python
# backend/app/services/llm_model_discovery.py
async def list_models_for_provider(provider: str, creds: ResolvedCredentials) -> list[str]:
    """Live model list from the provider API using resolved credentials.
    Raises on auth failure — callers map that to validation_status='invalid'."""
    # the gemini/openai/azure/anthropic branches, taking creds.api_key /
    # creds.base_url / creds.extra_config instead of raw env/settings
```

- [ ] **Step 2: Add failing test cases** to `test_admin_ai_settings_routes.py`.

```python
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_validate_marks_status(admin_client, monkeypatch):
    from app.services import llm_model_discovery
    monkeypatch.setattr(llm_model_discovery, "list_models_for_provider",
                        AsyncMock(return_value=["gpt-5.4", "gpt-5.4-mini"]))
    await admin_client.put("/api/admin/ai-settings/providers/openai", json={
        "isEnabled": True, "apiKey": "sk-x", "baseUrl": None,
        "extraConfig": {}, "curatedModels": []})
    resp = await admin_client.post("/api/admin/ai-settings/providers/openai/validate")
    assert resp.json()["validationStatus"] == "ok"


@pytest.mark.asyncio
async def test_discover_models_filters_by_search(admin_client, monkeypatch):
    from app.services import llm_model_discovery
    monkeypatch.setattr(llm_model_discovery, "list_models_for_provider",
                        AsyncMock(return_value=["gpt-5.4", "gpt-5.4-mini", "o3"]))
    await admin_client.put("/api/admin/ai-settings/providers/openai", json={
        "isEnabled": True, "apiKey": "sk-x", "baseUrl": None,
        "extraConfig": {}, "curatedModels": []})
    resp = await admin_client.post(
        "/api/admin/ai-settings/providers/openai/discover-models", json={"search": "mini"})
    assert resp.json()["models"] == ["gpt-5.4-mini"]
```

- [ ] **Step 3: Run → FAIL.**

- [ ] **Step 4: Add the 2 routes** to `admin_ai_settings.py`.

```python
@router.post("/providers/{provider}/discover-models", response_model=ModelSearchResponse)
async def discover_models(
    body: ModelSearchRequest, provider: str = Path(...),
    auth: AuthContext = require_permission("configuration:edit"),
    db: AsyncSession = Depends(get_db),
):
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    from app.services.llm_credentials import resolve_llm_credentials
    from app.services.llm_model_discovery import list_models_for_provider
    creds = await resolve_llm_credentials(db, auth.tenant_id, provider)
    models = await list_models_for_provider(provider, creds)
    search = (body.search or "").strip().lower()
    if search:
        models = [m for m in models if search in m.lower()]
    return ModelSearchResponse(models=models)


@router.post("/providers/{provider}/validate", response_model=ValidateResponse)
async def validate_provider(
    provider: str = Path(...),
    auth: AuthContext = require_permission("configuration:edit"),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    from app.services.llm_credentials import ProviderNotConfiguredError, resolve_llm_credentials
    from app.services.llm_model_discovery import list_models_for_provider
    row = (await db.execute(select(TenantLlmProvider).where(
        TenantLlmProvider.tenant_id == auth.tenant_id,
        TenantLlmProvider.provider == provider))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Provider {provider} not configured")
    try:
        creds = await resolve_llm_credentials(db, auth.tenant_id, provider)
        await list_models_for_provider(provider, creds)
        row.validation_status, detail = "ok", None
    except (ProviderNotConfiguredError, ValueError) as exc:  # missing/invalid tenant config — tenant's concern, surface cleanly
        row.validation_status, detail = "invalid", str(exc)[:300]
    row.last_validated_at = datetime.now(timezone.utc)
    await db.commit()
    return ValidateResponse(validation_status=row.validation_status, detail=detail)
```
Add the `ModelSearchRequest`/`ModelSearchResponse`/`ValidateResponse` imports at the top of the file.

- [ ] **Step 5: Run → PASS.**

- [ ] **Step 6: Commit.** `git add backend/app/routes/admin_ai_settings.py backend/app/services/llm_model_discovery.py backend/app/routes/llm.py backend/tests/test_admin_ai_settings_routes.py && git commit -m "feat(llm-byok): discover-models + validate routes; extract llm_model_discovery"`

---

## Task 4: Rewrite `routes/llm.py` `auth-status`

**Files:** Modify `backend/app/routes/llm.py` (`auth-status`, lines 33-47). Test `backend/tests/test_llm_routes.py`.

- [ ] **Step 1: Write the failing test.**

```python
# backend/tests/test_llm_routes.py
import pytest


@pytest.mark.asyncio
async def test_auth_status_reflects_tenant_providers(client, db_session, seeded_tenant):
    from app.models.tenant_llm_provider import TenantLlmProvider
    from app.services.llm_credentials.crypto import encrypt_secret
    db_session.add(TenantLlmProvider(
        tenant_id=seeded_tenant.id, provider="openai", is_enabled=True,
        api_key_encrypted=encrypt_secret("sk-x")))
    await db_session.commit()
    resp = await client.get("/api/llm/auth-status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["openai"] is True and body["anthropic"] is False
```

- [ ] **Step 2: Run → FAIL** (current route reads env vars).

- [ ] **Step 3: Rewrite `auth-status`.**

```python
@router.get("/auth-status")
async def auth_status(
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    from app.models.tenant_llm_provider import TenantLlmProvider
    rows = {r.provider: r for r in (await db.execute(
        select(TenantLlmProvider).where(TenantLlmProvider.tenant_id == auth.tenant_id)
    )).scalars()}
    def _ok(p: str) -> bool:
        r = rows.get(p)
        return bool(r and r.is_enabled and r.api_key_encrypted)
    return {p: _ok(p) for p in ("openai", "azure_openai", "anthropic", "gemini")}
```
Ensure `get_auth_context`, `get_db`, `select` are imported. The `/discover-models` + `/models` routes stay for now (they delegate to `llm_model_discovery`) — they are deleted in Phase 3 when `modelDiscovery.ts` goes.

- [ ] **Step 4: Run → PASS.** Verify `grep -rn "settings\.\(GEMINI\|OPENAI\|AZURE_OPENAI\|ANTHROPIC\)" backend/app/routes/llm.py` → zero hits.

- [ ] **Step 5: Commit.** `git add backend/app/routes/llm.py backend/tests/test_llm_routes.py && git commit -m "feat(llm-byok): rewrite routes/llm.py auth-status around tenant_llm_providers"`

---

## Task 5: Server-side LLM-assist endpoints

**Files:** Create `backend/app/services/llm_assist_service.py`, `backend/app/routes/llm_assist.py`; register the router. Test `backend/tests/test_llm_assist_routes.py`.

**Why:** the 7 client-side surfaces (Phase 3 Task 4) currently call Gemini from the browser using a plaintext key. In BYOK the key never reaches the browser, so the work moves server-side. Three endpoints replace all 7.

**Contract — all under `/api/llm/assist`, bearer-auth, every request carries explicit `provider` + `model`:**
- `POST /generate-prompt` — `GeneratePromptRequest` → `GeneratePromptResponse`
- `POST /generate-schema` — `GenerateSchemaRequest` → `GenerateSchemaResponse`
- `POST /extract-structured` — `ExtractStructuredRequest` → `ExtractStructuredResponse`

Each resolves credentials via `resolve_llm_credentials(db, auth.tenant_id, body.provider)`, builds a provider via `llm_base.py`, runs the task. Behaviour preserved from the old client pipeline: JSON-schema enforcement for schema/extraction, timeout, provider-error mapping (401/403/429 → clean message), token usage recorded via `LoggingLLMWrapper` (so cost tracking still gets a `fact_llm_generation` row).

- [ ] **Step 1: Write the failing test.**

```python
# backend/tests/test_llm_assist_routes.py
from unittest.mock import AsyncMock
import pytest


@pytest.mark.asyncio
async def test_generate_prompt(client, monkeypatch, seeded_provider_openai):
    from app.services import llm_assist_service
    monkeypatch.setattr(llm_assist_service, "run_generate_prompt",
                        AsyncMock(return_value="You are a transcription evaluator..."))
    resp = await client.post("/api/llm/assist/generate-prompt", json={
        "provider": "openai", "model": "gpt-5.4",
        "promptType": "evaluation", "userIdea": "check tone"})
    assert resp.status_code == 200
    assert resp.json()["prompt"].startswith("You are")


@pytest.mark.asyncio
async def test_generate_schema_returns_object(client, monkeypatch, seeded_provider_openai):
    from app.services import llm_assist_service
    monkeypatch.setattr(llm_assist_service, "run_generate_schema",
                        AsyncMock(return_value={"type": "object", "properties": {}}))
    resp = await client.post("/api/llm/assist/generate-schema", json={
        "provider": "openai", "model": "gpt-5.4",
        "promptType": "extraction", "userIdea": "extract name and age"})
    assert resp.json()["schema"]["type"] == "object"


@pytest.mark.asyncio
async def test_assist_unconfigured_provider_returns_4xx(client, seeded_tenant):
    resp = await client.post("/api/llm/assist/generate-prompt", json={
        "provider": "anthropic", "model": "claude", "promptType": "evaluation",
        "userIdea": "x"})
    assert resp.status_code in (400, 409)  # ProviderNotConfiguredError mapped cleanly
```

> `seeded_provider_openai`: a fixture that inserts an enabled `openai` `TenantLlmProvider` row for the test tenant — add it to `conftest.py` or inline it like the resolver tests do.

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Write `llm_assist_service.py`.** Three async functions — `run_generate_prompt`, `run_generate_schema`, `run_extract_structured` — each takes `(creds: ResolvedCredentials, model: str, ...)`, builds a provider through `llm_base.py` (the same wrappers evaluators use), and runs the task. Port the system prompts: the old client constants `PROMPT_GENERATOR_SYSTEM_PROMPT` and `SCHEMA_GENERATOR_SYSTEM_PROMPT` (currently in the frontend) move here as Python constants. Schema/extraction calls enforce JSON output. Wrap the provider in `LoggingLLMWrapper` + `make_usage_callback()` (per CLAUDE.md) so usage is recorded.

> Read `backend/app/services/evaluators/llm_base.py` and `backend/app/services/evaluators/runner_utils.py` first — reuse the provider factory + `LoggingLLMWrapper` pattern; do not hand-roll provider construction.

- [ ] **Step 4: Write `llm_assist.py` router.**

```python
# backend/app/routes/llm_assist.py
"""Server-side LLM-assist endpoints. Replace the old browser-side pipeline —
the encrypted key never leaves the backend."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthContext, get_auth_context
from app.database import get_db
from app.schemas.llm_assist import (
    ExtractStructuredRequest, ExtractStructuredResponse,
    GeneratePromptRequest, GeneratePromptResponse,
    GenerateSchemaRequest, GenerateSchemaResponse)
from app.services.llm_credentials import ProviderNotConfiguredError, resolve_llm_credentials
from app.services import llm_assist_service

router = APIRouter(prefix="/api/llm/assist", tags=["llm-assist"])


async def _creds(db, auth, provider):
    try:
        return await resolve_llm_credentials(db, auth.tenant_id, provider)
    except ProviderNotConfiguredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/generate-prompt", response_model=GeneratePromptResponse)
async def generate_prompt(
    body: GeneratePromptRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    creds = await _creds(db, auth, body.provider)
    prompt = await llm_assist_service.run_generate_prompt(
        creds=creds, model=body.model, prompt_type=body.prompt_type,
        user_idea=body.user_idea, tenant_id=auth.tenant_id, user_id=auth.user_id)
    return GeneratePromptResponse(prompt=prompt)


@router.post("/generate-schema", response_model=GenerateSchemaResponse)
async def generate_schema(
    body: GenerateSchemaRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    creds = await _creds(db, auth, body.provider)
    schema = await llm_assist_service.run_generate_schema(
        creds=creds, model=body.model, prompt_type=body.prompt_type,
        user_idea=body.user_idea, tenant_id=auth.tenant_id, user_id=auth.user_id)
    return GenerateSchemaResponse(schema=schema)


@router.post("/extract-structured", response_model=ExtractStructuredResponse)
async def extract_structured(
    body: ExtractStructuredRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    creds = await _creds(db, auth, body.provider)
    return await llm_assist_service.run_extract_structured(
        creds=creds, model=body.model, body=body,
        tenant_id=auth.tenant_id, user_id=auth.user_id)
```
Register the router. Add `llm_assist` to the `CLAUDE.md` route-groups list + count.

- [ ] **Step 5: Run → PASS.**

- [ ] **Step 6: Commit.** `git add backend/app/routes/llm_assist.py backend/app/services/llm_assist_service.py backend/tests/test_llm_assist_routes.py CLAUDE.md && git commit -m "feat(llm-byok): server-side LLM-assist endpoints (prompt/schema/extraction)"`

---

## Task 6: Frontend API client + TanStack hooks

**Files:** Create `src/services/api/aiSettingsApi.ts`, `src/services/api/aiSettingsQueries.ts`. Test `src/services/api/aiSettingsQueries.test.ts`.

> Hooks go in `services/api/` (not `features/admin/`) so the Phase-3 `components/ui/LLMConfigSection` can import `useProviderConfigs` without a `ui → features` layering violation. This is intentional for this self-contained BYOK plan because Platform Phase 15 is deferred.

- [ ] **Step 1: Write the API client.** Match the actual `apiRequest` signature in `src/services/api/client.ts` (read it first — confirm how it takes method/body).

```typescript
// src/services/api/aiSettingsApi.ts
import { apiRequest } from '@/services/api/client';

export type LLMProvider = 'openai' | 'azure_openai' | 'anthropic' | 'gemini';

export interface ProviderConfig {
  provider: LLMProvider;
  isEnabled: boolean;
  hasApiKey: boolean;
  baseUrl: string | null;
  extraConfig: Record<string, unknown>;
  curatedModels: string[];
  validationStatus: 'ok' | 'invalid' | 'untested';
  lastValidatedAt: string | null;
}

export interface ProviderConfigUpsert {
  isEnabled: boolean;
  apiKey: string;            // '' => preserve stored key
  baseUrl: string | null;
  extraConfig: Record<string, unknown>;
  curatedModels: string[];
}

export const aiSettingsApi = {
  list: () => apiRequest<ProviderConfig[]>('/api/admin/ai-settings/providers'),
  upsert: (provider: LLMProvider, body: ProviderConfigUpsert) =>
    apiRequest<ProviderConfig>(`/api/admin/ai-settings/providers/${provider}`,
      { method: 'PUT', body: JSON.stringify(body) }),
  discoverModels: (provider: LLMProvider, search: string) =>
    apiRequest<{ models: string[] }>(
      `/api/admin/ai-settings/providers/${provider}/discover-models`,
      { method: 'POST', body: JSON.stringify({ search }) }),
  validate: (provider: LLMProvider) =>
    apiRequest<{ validationStatus: string; detail: string | null }>(
      `/api/admin/ai-settings/providers/${provider}/validate`, { method: 'POST' }),
};
```

- [ ] **Step 2: Write the hooks.** Wire through `apiQueryFn` from `src/features/orchestration/queries/queryFn.ts` per the CLAUDE.md TanStack rule.

```typescript
// src/services/api/aiSettingsQueries.ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { aiSettingsApi, type LLMProvider, type ProviderConfigUpsert } from './aiSettingsApi';

const KEY = ['admin', 'ai-settings', 'providers'] as const;

export function useProviderConfigs() {
  return useQuery({ queryKey: KEY, queryFn: () => aiSettingsApi.list() });
}

export function useUpsertProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ provider, body }: { provider: LLMProvider; body: ProviderConfigUpsert }) =>
      aiSettingsApi.upsert(provider, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useValidateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (provider: LLMProvider) => aiSettingsApi.validate(provider),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
```

- [ ] **Step 3: Write a hook test** — mount `useProviderConfigs` with a mocked `apiRequest`, assert query key + shape. Follow an existing query test in the repo.

- [ ] **Step 4: Lint + types + test.** `npm run lint && npx tsc -b && npx vitest run src/services/api/aiSettingsQueries.test.ts`.

- [ ] **Step 5: Commit.** `git add src/services/api/aiSettingsApi.ts src/services/api/aiSettingsQueries.ts src/services/api/aiSettingsQueries.test.ts && git commit -m "feat(llm-byok): aiSettings API client + TanStack hooks"`

---

## Task 7: Admin AI Settings page — shell + provider rail

**Files:** Create `src/features/admin/pages/AdminAISettingsPage.tsx`, `src/features/admin/components/aiSettings/ProviderRail.tsx`; modify `src/config/routes.ts` + admin nav.

**Layout — match the approved reference exactly:** two columns. Left "Providers" rail: one card per provider (`OpenAI`, `Azure OpenAI`, `Anthropic`, `Gemini`) with icon, name, enable toggle. Right: the config panel (Task 8). Header: "Model Providers" / "Enable providers and configure API keys to access AI models." Design-system tokens only — no hex; `cn()` for conditional classes.

- [ ] **Step 1: Build `ProviderRail.tsx`.** Renders the 4 provider cards from `useProviderConfigs()`. Each card: icon + label + a toggle bound to `isEnabled` (toggling fires `useUpsertProvider` with the current config + flipped `isEnabled` + blank `apiKey` to preserve the key). Selecting a card sets the active provider in page state. Small `validationStatus` dot (`ok`/`invalid`/`untested` → success/error/muted tokens).

- [ ] **Step 2: Build `AdminAISettingsPage.tsx` shell.** Two-column flex inside the admin `PageSurface` (follow `src/features/admin/pages/*`). Left `<ProviderRail selected onSelect />`, right `<ProviderConfigPanel provider={selected} />` (placeholder until Task 8). Local state `selectedProvider` (default `'openai'`).

- [ ] **Step 3: Wire the route.** In `src/config/routes.ts` add `admin.aiSettings: '/admin/ai-settings'`; register in the admin router + admin nav, gated like `AdminUsersPage`/`RolesTab`.

- [ ] **Step 4: Lint + types + visual.** `npm run lint && npx tsc -b`. Dev server: `/admin/ai-settings` renders 4 providers; toggles persist (network tab shows `PUT`); layout matches the reference; light + dark mode.

- [ ] **Step 5: Commit.** `git add src/features/admin/pages/AdminAISettingsPage.tsx src/features/admin/components/aiSettings/ProviderRail.tsx src/config/routes.ts && git commit -m "feat(llm-byok): Admin AI Settings page shell + provider rail"`

---

## Task 8: Provider config panel + model curation

**Files:** Create `src/features/admin/components/aiSettings/ProviderConfigPanel.tsx`, `src/features/admin/components/aiSettings/ModelCuration.tsx`.

**Panel (match the reference):** API Key (password input, show/copy; placeholder `••••` when `hasApiKey` and untouched; blank submit preserves the key — helper text "Leave blank to keep the current key"); Base URL (label "Azure Endpoint", `azure_openai` only); Azure api-version (text, `azure_openai` only, bound to `extraConfig.api_version`); `<ModelCuration>`; Test-key button (`useValidateProvider`, render status badge + `detail` via `notificationService`); Save button (`useUpsertProvider` with the panel state).

- [ ] **Step 1: Build `ModelCuration.tsx`.** Props: `provider`, `curatedModels`, `onChange(models)`. Search input + Search button → `aiSettingsApi.discoverModels(provider, search)`; results render as add-able rows; "Selected Models (N)" list with remove (trash) action. **Does NOT use `ModelSelector`** — that component is deleted in Phase 3; this is built fresh against `aiSettingsApi.discoverModels`.

- [ ] **Step 2: Build `ProviderConfigPanel.tsx`.** Reads the active provider's `ProviderConfig` from `useProviderConfigs()`; local form state seeded from it; conditionally renders Base URL + api-version for `azure_openai`; wires Save + Test-key.

- [ ] **Step 3: Mount it** — replace the placeholder in `AdminAISettingsPage.tsx` with `<ProviderConfigPanel provider={selectedProvider} />`.

- [ ] **Step 4: Lint + types + full visual.** `npm run lint && npx tsc -b`. Dev server: enter a real key, Save, Test → `ok`; search + add models → persist after reload; blank-save preserves the key; Azure shows endpoint + api-version, others don't; light + dark mode.

- [ ] **Step 5: Commit.** `git add src/features/admin/components/aiSettings/ProviderConfigPanel.tsx src/features/admin/components/aiSettings/ModelCuration.tsx src/features/admin/pages/AdminAISettingsPage.tsx && git commit -m "feat(llm-byok): provider config panel + model curation"`

---

## Phase 2 Done — Verification Checklist

- [ ] `grep -rn "settings\.\(GEMINI\|OPENAI\|AZURE_OPENAI\|ANTHROPIC\|DEFAULT_LLM\)" backend/app/routes/llm.py` → zero hits
- [ ] Backend suite green: `pytest backend/tests/test_admin_ai_settings_routes.py backend/tests/test_llm_routes.py backend/tests/test_ai_settings_schemas.py backend/tests/test_llm_assist_routes.py -v`
- [ ] `npm run lint && npx tsc -b` clean
- [ ] Admin can enable a provider, save a key, test it (→ `ok`), curate models — all persist across reload
- [ ] Non-admin gets 403 on PUT/validate/discover
- [ ] API key never appears in any GET response (network-tab check)
- [ ] The 3 `/api/llm/assist/*` endpoints respond (tested via the suite); old client-side path still in use until Phase 3
- [ ] All Phase 2 commits are on `feat/llm-credentials-cleanup`; lint + types + the named test files are green. Do NOT merge to `main` — proceed to Phase 3 on the same branch only once this checklist is fully green.
