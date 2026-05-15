# Phase 1 — Backend Foundation

> **Status: ✅ COMPLETE — landed on `feat/llm-credentials-cleanup` 2026-05-16, branch head `9252a76`. Do not re-run.** All 13 task commits below are merged on the shared branch. Phase 2 continues on the same branch — see the [Phase 1 → Phase 2 handoff brief in README.md](README.md#phase-1--phase-2-handoff-brief) for inherited contracts, deltas from this plan, and the `LLM_CREDENTIAL_KEY` deploy prerequisite before Phase 2 ships.

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Stand up `platform.tenant_llm_providers` + Fernet crypto + `resolve_llm_credentials` + the `LLM_CREDENTIAL_KEY` boot guard; rewire all 14 `get_llm_settings_from_db` call sites; make the two no-provider jobs carry provider/model in job params; delete `settings_helper.py`; remove tenant credential env fallbacks. After this phase the backend resolves every real-tenant LLM credential from the new table. Old `application_settings` `llm-settings` rows are **kept** (deleted in Phase 3) so the legacy frontend `llmSettingsStore` keeps functioning untouched until the self-contained frontend cleanup.

**Branch:** Phase 1 **creates** the shared branch — from an up-to-date `main`, run `git checkout -b feat/llm-credentials-cleanup`. ALL work for this phase **and Phases 2-3** lives on this one branch. Commit every task here. Do NOT merge to `main` and do NOT create any other branch — the whole feature merges as one branch after Phase 3.

**Test command:** `pyenv activate venv-python-ai-evals-arize && PYTHONPATH=backend python -m pytest backend/tests/<file> -v`

**Scope note:** This phase is backend-only **except** one small bridging edit to `CreateEvaluatorWizard.tsx` (Task 9) — required so the evaluator-draft flow keeps working once its handler reads provider/model from job params.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/services/llm_credentials/__init__.py` | Package; re-exports `resolve_llm_credentials`, `ResolvedCredentials`, `ProviderNotConfiguredError`, `invalidate_cache`. |
| `backend/app/services/llm_credentials/crypto.py` | Fernet encrypt/decrypt for `api_key_encrypted`, keyed by `LLM_CREDENTIAL_KEY`. |
| `backend/app/services/llm_credentials/resolver.py` | `resolve_llm_credentials`, `ResolvedCredentials`, `ProviderNotConfiguredError`, `invalidate_cache`, 60s cache. |
| `backend/app/models/tenant_llm_provider.py` | `TenantLlmProvider` ORM model. |
| `backend/alembic/versions/0047_tenant_llm_providers.py` | Create table + backfill from `application_settings`. |
| `backend/app/services/evaluators/settings_helper.py` | **Deleted.** |
| `backend/app/config.py` | Remove tenant credential/model fallback fields no runtime code reads after rewiring; add `LLM_CREDENTIAL_KEY`; keep the Gemini system-tenant service-account path. |
| `backend/app/main.py` | `_validate_startup_config` gains the `LLM_CREDENTIAL_KEY` round-trip check. |

---

## Task 1: `LLM_CREDENTIAL_KEY` config field

**Files:** Modify `backend/app/config.py` (after line 91, the `ORCHESTRATION_CONNECTION_KEY` block).

- [ ] **Step 1: Add the field.** After `ORCHESTRATION_CONNECTION_KEY: str = ""` (line 91), add:

```python

    # Process-level Fernet key encrypting platform.tenant_llm_providers
    # api_key_encrypted blobs. Required — validated on startup. Loss = all
    # tenant LLM keys become unreadable; back it up like JWT_SECRET.
    LLM_CREDENTIAL_KEY: str = ""
```

- [ ] **Step 2: Verify it loads.** Run: `PYTHONPATH=backend python -c "from app.config import settings; print(hasattr(settings, 'LLM_CREDENTIAL_KEY'))"` → `True`.

- [ ] **Step 3: Commit.** `git add backend/app/config.py && git commit -m "feat(llm-byok): add LLM_CREDENTIAL_KEY config field"`

---

## Task 2: Fernet crypto module

**Files:**
- Create `backend/app/services/llm_credentials/__init__.py`, `backend/app/services/llm_credentials/crypto.py`
- Test `backend/tests/test_llm_credentials_crypto.py`

- [ ] **Step 1: Write the failing test.**

```python
# backend/tests/test_llm_credentials_crypto.py
"""Round-trip + tamper tests for LLM credential Fernet crypto."""
import pytest
from cryptography.fernet import Fernet


def test_encrypt_decrypt_round_trip(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "LLM_CREDENTIAL_KEY", Fernet.generate_key().decode())
    from app.services.llm_credentials import crypto
    token = crypto.encrypt_secret("sk-test-abc123")
    assert token != "sk-test-abc123"
    assert crypto.decrypt_secret(token) == "sk-test-abc123"


def test_decrypt_rejects_tampered_token(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "LLM_CREDENTIAL_KEY", Fernet.generate_key().decode())
    from app.services.llm_credentials import crypto
    with pytest.raises(crypto.LlmCredentialCryptoError):
        crypto.decrypt_secret("not-a-real-token")


def test_missing_key_raises(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "LLM_CREDENTIAL_KEY", "")
    from app.services.llm_credentials import crypto
    with pytest.raises(crypto.LlmCredentialCryptoError):
        crypto.encrypt_secret("anything")


def test_assert_key_valid_round_trips(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "LLM_CREDENTIAL_KEY", Fernet.generate_key().decode())
    from app.services.llm_credentials import crypto
    crypto.assert_key_valid()  # must not raise
```

- [ ] **Step 2: Run → FAIL.** `PYTHONPATH=backend python -m pytest backend/tests/test_llm_credentials_crypto.py -v` — `ModuleNotFoundError`.

- [ ] **Step 3: Create `__init__.py` (docstring only — re-exports added in Task 6).**

```python
# backend/app/services/llm_credentials/__init__.py
"""LLM credential storage, encryption, and resolution."""
```

- [ ] **Step 4: Create `crypto.py`.**

```python
# backend/app/services/llm_credentials/crypto.py
"""Fernet encrypt/decrypt for tenant_llm_providers.api_key_encrypted.

One process-level key from ``settings.LLM_CREDENTIAL_KEY``. Mirrors
``orchestration/connections/crypto.py`` — same pattern, separate key so the
two credential domains rotate independently.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class LlmCredentialCryptoError(RuntimeError):
    """Raised when LLM_CREDENTIAL_KEY is missing/invalid or a blob fails to decrypt."""


def _fernet() -> Fernet:
    key = settings.LLM_CREDENTIAL_KEY
    if not key:
        raise LlmCredentialCryptoError("LLM_CREDENTIAL_KEY environment variable is required.")
    try:
        return Fernet(key.encode("utf-8") if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise LlmCredentialCryptoError(
            "LLM_CREDENTIAL_KEY is not a valid urlsafe-base64 32-byte Fernet key."
        ) from exc


def encrypt_secret(plaintext: str) -> str:
    """Encrypt an API key string. Returns a urlsafe-base64 token (str)."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str:
    """Reverse of ``encrypt_secret``. Raises ``LlmCredentialCryptoError`` on tamper / wrong key."""
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise LlmCredentialCryptoError("LLM credential blob failed to decrypt") from exc


def assert_key_valid() -> None:
    """Boot-time check — call from the lifespan validator."""
    f = _fernet()
    f.decrypt(f.encrypt(b"ok"))
```

- [ ] **Step 5: Run → PASS.** Same command as Step 2 — 4 tests pass.

- [ ] **Step 6: Commit.** `git add backend/app/services/llm_credentials/ backend/tests/test_llm_credentials_crypto.py && git commit -m "feat(llm-byok): Fernet crypto module for LLM credentials"`

---

## Task 3: `LLM_CREDENTIAL_KEY` boot validation

**Files:** Modify `backend/app/main.py:39-58` (`_validate_startup_config`). Test `backend/tests/test_llm_credential_key_boot.py`.

- [ ] **Step 1: Write the failing test.**

```python
# backend/tests/test_llm_credential_key_boot.py
"""Boot validator must reject a missing/invalid LLM_CREDENTIAL_KEY."""
import pytest
from cryptography.fernet import Fernet


def _base_env(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "JWT_SECRET", "x", raising=False)
    monkeypatch.setattr(settings, "ORCHESTRATION_CONNECTION_KEY",
                        Fernet.generate_key().decode(), raising=False)
    return settings


def test_boot_rejects_missing_llm_credential_key(monkeypatch):
    settings = _base_env(monkeypatch)
    monkeypatch.setattr(settings, "LLM_CREDENTIAL_KEY", "", raising=False)
    from app.main import _validate_startup_config
    with pytest.raises(RuntimeError, match="LLM_CREDENTIAL_KEY"):
        _validate_startup_config()


def test_boot_rejects_invalid_llm_credential_key(monkeypatch):
    settings = _base_env(monkeypatch)
    monkeypatch.setattr(settings, "LLM_CREDENTIAL_KEY", "not-base64", raising=False)
    from app.main import _validate_startup_config
    with pytest.raises(RuntimeError, match="LLM_CREDENTIAL_KEY is invalid"):
        _validate_startup_config()
```

- [ ] **Step 2: Run → FAIL.** `PYTHONPATH=backend python -m pytest backend/tests/test_llm_credential_key_boot.py -v`.

- [ ] **Step 3: Add the boot check.** In `_validate_startup_config`, **immediately after the `ORCHESTRATION_CONNECTION_KEY` block (after line 58) and BEFORE the `JOB_*` checks (line 59)**, insert:

```python
    if not settings.LLM_CREDENTIAL_KEY:
        raise RuntimeError(
            "LLM_CREDENTIAL_KEY environment variable is required. "
            "Generate one with `python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"` and add it to .env.backend."
        )
    from app.services.llm_credentials.crypto import (
        LlmCredentialCryptoError,
        assert_key_valid as assert_llm_key_valid,
    )
    try:
        assert_llm_key_valid()
    except LlmCredentialCryptoError as exc:
        raise RuntimeError(f"LLM_CREDENTIAL_KEY is invalid: {exc}") from exc
```

- [ ] **Step 4: Run → PASS.** Same command — 2 tests pass.

- [ ] **Step 5: Commit.** `git add backend/app/main.py backend/tests/test_llm_credential_key_boot.py && git commit -m "feat(llm-byok): boot-validate LLM_CREDENTIAL_KEY"`

---

## Task 4: `TenantLlmProvider` ORM model

**Files:** Create `backend/app/models/tenant_llm_provider.py`; modify `backend/app/models/__init__.py`. Test `backend/tests/test_tenant_llm_provider_model.py`.

- [ ] **Step 1: Write the failing test.**

```python
# backend/tests/test_tenant_llm_provider_model.py
def test_model_table_shape():
    from app.models.tenant_llm_provider import TenantLlmProvider
    t = TenantLlmProvider.__table__
    assert t.name == "tenant_llm_providers"
    assert t.schema == "platform"
    assert {
        "id", "tenant_id", "provider", "is_enabled", "api_key_encrypted",
        "base_url", "extra_config", "curated_models", "validation_status",
        "last_validated_at", "updated_by", "updated_at",
    }.issubset(set(t.columns.keys()))
    uniques = [c for c in t.constraints if c.__class__.__name__ == "UniqueConstraint"]
    assert any({"tenant_id", "provider"} == {col.name for col in u.columns} for u in uniques)
```

- [ ] **Step 2: Run → FAIL.** `PYTHONPATH=backend python -m pytest backend/tests/test_tenant_llm_provider_model.py -v`.

- [ ] **Step 3: Write the model.** Read `backend/app/models/application_setting.py` first for the local base class + conventions, then:

```python
# backend/app/models/tenant_llm_provider.py
"""Per-tenant LLM provider credentials and curated model list.

Replaces the per-user application_settings llm-settings blob. One row per
(tenant, provider). api_key_encrypted is Fernet ciphertext — never store or
return plaintext.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TenantLlmProvider(Base):
    __tablename__ = "tenant_llm_providers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_tenant_llm_provider"),
        Index("idx_tenant_llm_providers_tenant", "tenant_id"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform.tenants.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    curated_models: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    validation_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="untested", server_default="untested")
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform.users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

> If the repo's models use `CamelORMModel` instead of bare `Base`, use that and follow its conventions.

- [ ] **Step 4: Register the model.** In `backend/app/models/__init__.py`, add: `from app.models.tenant_llm_provider import TenantLlmProvider  # noqa: F401`

- [ ] **Step 5: Run → PASS.**

- [ ] **Step 6: Commit.** `git add backend/app/models/tenant_llm_provider.py backend/app/models/__init__.py backend/tests/test_tenant_llm_provider_model.py && git commit -m "feat(llm-byok): TenantLlmProvider ORM model"`

---

## Task 5: Migration 0047 — create table + backfill (old rows kept)

**Files:** Create `backend/alembic/versions/0047_tenant_llm_providers.py`. Test `backend/tests/test_migration_0047_tenant_llm_providers.py`.

> **Deploy prerequisite — flag this:** the backfill calls `encrypt_secret`, so `LLM_CREDENTIAL_KEY` MUST be set in the environment before `alembic upgrade head` runs (entrypoint.sh runs migrations on boot). Set it on the prod Container App **before** deploying the Phase-1 image. Missing or invalid key = migration failure before the backend serves traffic.
>
> **Rollback note:** this migration does NOT delete the old `application_settings` `llm-settings` rows — that is migration 0048 in Phase 3, giving a full rollback window. Downgrading 0047 drops `tenant_llm_providers`; the source data still exists in `application_settings` until Phase 3.

- [ ] **Step 1: Confirm latest revision.** `ls backend/alembic/versions/ | sort | tail -1` should show the current head, presently `0046_drop_fact_lead_signal_backfill_index.py`. New revision = `0047`, `down_revision = "0046_drop_fact_lead_signal_backfill_index"`. If a newer migration lands before implementation, use the next available revision and update this task before coding.

- [ ] **Step 2: Write the failing test.**

```python
# backend/tests/test_migration_0047_tenant_llm_providers.py
def test_revision_chains_off_current_head():
    import importlib
    mod = importlib.import_module("alembic.versions.0047_tenant_llm_providers")
    assert mod.revision == "0047"
    assert mod.down_revision == "0046_drop_fact_lead_signal_backfill_index"
    assert hasattr(mod, "upgrade") and hasattr(mod, "downgrade")
```

> If `alembic.versions` isn't an importable package in this repo's test setup, instead `Read` the file and assert the `revision`/`down_revision` literals. Match any existing `test_migration_*.py` convention.

- [ ] **Step 3: Run → FAIL.**

- [ ] **Step 4: Write the migration.**

```python
# backend/alembic/versions/0047_tenant_llm_providers.py
"""create platform.tenant_llm_providers + backfill from application_settings

Revision ID: 0047
Revises: 0046_drop_fact_lead_signal_backfill_index
Create Date: 2026-05-14

Backfill: for each tenant, take the most-recent application_settings row with
key='llm-settings', explode its per-provider keys into one tenant_llm_providers
row per provider that has a key. Keys are Fernet-encrypted with
LLM_CREDENTIAL_KEY. The old llm-settings rows are NOT deleted here (see 0048).
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0047"
down_revision = "0046_drop_fact_lead_signal_backfill_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_llm_providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("extra_config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("curated_models", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("validation_status", sa.String(16), nullable=False, server_default="untested"),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["platform.tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["platform.users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "provider", name="uq_tenant_llm_provider"),
        schema="platform",
    )
    op.create_index("idx_tenant_llm_providers_tenant", "tenant_llm_providers",
                    ["tenant_id"], schema="platform")

    from app.services.llm_credentials.crypto import encrypt_secret

    conn = op.get_bind()
    rows = conn.execute(sa.text("""
        SELECT DISTINCT ON (tenant_id) tenant_id, value
        FROM platform.application_settings
        WHERE key = 'llm-settings'
        ORDER BY tenant_id, updated_at DESC
    """)).fetchall()

    provider_map = [
        ("geminiApiKey", "gemini"),
        ("openaiApiKey", "openai"),
        ("anthropicApiKey", "anthropic"),
        ("azureOpenaiApiKey", "azure_openai"),
    ]

    for tenant_id, value in rows:
        if not value:
            continue
        if isinstance(value, str):
            value = json.loads(value)
        selected_model = value.get("selectedModel", "")
        for json_key, provider in provider_map:
            api_key = (value.get(json_key) or "").strip()
            if not api_key:
                continue
            extra_config = {}
            base_url = None
            if provider == "azure_openai":
                extra_config["api_version"] = value.get("azureOpenaiApiVersion") or "2025-04-01-preview"
                deployments = value.get("azureOpenaiDeployments") or []
                if isinstance(deployments, str):
                    deployments = [d.strip() for d in deployments.split(",") if d.strip()]
                extra_config["deployments"] = deployments
                base_url = value.get("azureOpenaiEndpoint")
                curated = deployments or ([selected_model] if selected_model else [])
            else:
                curated = [selected_model] if selected_model else []
            conn.execute(sa.text("""
                INSERT INTO platform.tenant_llm_providers
                    (id, tenant_id, provider, is_enabled, api_key_encrypted,
                     base_url, extra_config, curated_models, validation_status)
                VALUES
                    (:id, :tenant_id, :provider, true, :api_key_encrypted,
                     :base_url, CAST(:extra_config AS JSONB), CAST(:curated AS JSONB), 'untested')
                ON CONFLICT (tenant_id, provider) DO NOTHING
            """), {
                "id": str(uuid.uuid4()),
                "tenant_id": str(tenant_id),
                "provider": provider,
                "api_key_encrypted": encrypt_secret(api_key),
                "base_url": base_url,
                "extra_config": json.dumps(extra_config),
                "curated": json.dumps(curated),
            })


def downgrade() -> None:
    op.drop_index("idx_tenant_llm_providers_tenant", table_name="tenant_llm_providers", schema="platform")
    op.drop_table("tenant_llm_providers", schema="platform")
```

- [ ] **Step 5: Run the migration.** With `LLM_CREDENTIAL_KEY` set in `.env.backend`: `cd backend && alembic upgrade head` → clean. Then `alembic downgrade -1 && alembic upgrade head` → clean.

- [ ] **Step 6: Run the test → PASS.**

- [ ] **Step 7: Commit.** `git add backend/alembic/versions/0047_tenant_llm_providers.py backend/tests/test_migration_0047_tenant_llm_providers.py && git commit -m "feat(llm-byok): migration 0047 — tenant_llm_providers + backfill"`

---

## Task 6: `resolve_llm_credentials` resolver

**Files:** Create `backend/app/services/llm_credentials/resolver.py`; replace `__init__.py` with the re-export version. Test `backend/tests/test_llm_credentials_resolver.py`.

**Contract:**
```python
@dataclass(frozen=True)
class ResolvedCredentials:
    provider: str                     # 'openai' | 'azure_openai' | 'anthropic' | 'gemini'
    api_key: str                      # plaintext; "" only when service_account_path is set
    base_url: str | None              # Azure endpoint / self-hosted base URL
    extra_config: dict                # e.g. {"api_version": "..."} for azure
    service_account_path: str | None  # set ONLY for system-tenant gemini SA fallback
```

- [ ] **Step 1: Write the failing test.**

```python
# backend/tests/test_llm_credentials_resolver.py
"""resolve_llm_credentials: enabled tenant row -> system-tenant SA -> ProviderNotConfiguredError."""
import pytest
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "LLM_CREDENTIAL_KEY", Fernet.generate_key().decode(), raising=False)


async def _seed(db, tenant_id, provider, api_key, **kw):
    from app.models.tenant_llm_provider import TenantLlmProvider
    from app.services.llm_credentials.crypto import encrypt_secret
    db.add(TenantLlmProvider(
        tenant_id=tenant_id, provider=provider, is_enabled=kw.get("is_enabled", True),
        api_key_encrypted=encrypt_secret(api_key) if api_key else None,
        base_url=kw.get("base_url"), extra_config=kw.get("extra_config", {}),
        curated_models=kw.get("curated_models", []),
    ))
    await db.commit()


@pytest.mark.asyncio
async def test_resolves_enabled_tenant_row(db_session, seeded_tenant):
    from app.services.llm_credentials import resolve_llm_credentials
    await _seed(db_session, seeded_tenant.id, "openai", "sk-live-xyz")
    creds = await resolve_llm_credentials(db_session, seeded_tenant.id, "openai")
    assert creds.provider == "openai" and creds.api_key == "sk-live-xyz"
    assert creds.service_account_path is None


@pytest.mark.asyncio
async def test_disabled_row_is_not_resolved(db_session, seeded_tenant):
    from app.services.llm_credentials import ProviderNotConfiguredError, resolve_llm_credentials
    await _seed(db_session, seeded_tenant.id, "openai", "sk-x", is_enabled=False)
    with pytest.raises(ProviderNotConfiguredError):
        await resolve_llm_credentials(db_session, seeded_tenant.id, "openai")


@pytest.mark.asyncio
async def test_unconfigured_provider_raises(db_session, seeded_tenant):
    from app.services.llm_credentials import ProviderNotConfiguredError, resolve_llm_credentials
    with pytest.raises(ProviderNotConfiguredError):
        await resolve_llm_credentials(db_session, seeded_tenant.id, "anthropic")


@pytest.mark.asyncio
async def test_system_tenant_gemini_falls_back_to_env_sa(db_session, monkeypatch, tmp_path):
    from app.constants import SYSTEM_TENANT_ID
    from app.config import settings
    sa = tmp_path / "sa.json"; sa.write_text("{}")
    monkeypatch.setattr(settings, "GEMINI_SERVICE_ACCOUNT_PATH", str(sa))
    from app.services.llm_credentials import resolve_llm_credentials
    creds = await resolve_llm_credentials(db_session, SYSTEM_TENANT_ID, "gemini")
    assert creds.service_account_path == str(sa) and creds.api_key == ""


@pytest.mark.asyncio
async def test_real_tenant_gemini_never_uses_env_sa(db_session, seeded_tenant, monkeypatch, tmp_path):
    from app.config import settings
    from app.services.llm_credentials import ProviderNotConfiguredError, resolve_llm_credentials
    sa = tmp_path / "sa.json"; sa.write_text("{}")
    monkeypatch.setattr(settings, "GEMINI_SERVICE_ACCOUNT_PATH", str(sa))
    with pytest.raises(ProviderNotConfiguredError):
        await resolve_llm_credentials(db_session, seeded_tenant.id, "gemini")
```

> `db_session` / `seeded_tenant`: reuse the async-session + tenant fixtures from `backend/tests/conftest.py`. Adapt names to whatever exists there.

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Write `resolver.py`.**

```python
# backend/app/services/llm_credentials/resolver.py
"""The single read path for LLM provider credentials.

resolve_llm_credentials(db, tenant_id, provider):
  enabled tenant row with a key -> decrypt, return ResolvedCredentials
  gemini + no key + tenant IS the system tenant -> env service-account path
  otherwise -> ProviderNotConfiguredError

No user_id. No auth_intent. No provider_override. Callers pass the provider
they already hold and get credentials only — the model name is the caller's
concern.
"""
from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.constants import SYSTEM_TENANT_ID
from app.models.tenant_llm_provider import TenantLlmProvider
from app.services.llm_credentials.crypto import decrypt_secret


class ProviderNotConfiguredError(RuntimeError):
    """Raised when a tenant has no usable credential for the requested provider.

    Carries a stable client-facing message — surface it as the HTTPException
    detail so the UI can show "configure <provider> in AI Settings".
    """

    def __init__(self, provider: str):
        self.provider = provider
        super().__init__(
            f"LLM provider '{provider}' is not configured for this tenant. "
            f"An admin must enable it in AI Settings."
        )


@dataclass(frozen=True)
class ResolvedCredentials:
    provider: str
    api_key: str
    base_url: str | None
    extra_config: dict
    service_account_path: str | None


_CACHE: dict[tuple[str, str], tuple[float, ResolvedCredentials]] = {}
_CACHE_TTL_SECONDS = 60.0


def invalidate_cache(tenant_id: uuid.UUID | str, provider: str | None = None) -> None:
    """Drop cached credentials. Call after any admin write to a provider row."""
    tid = str(tenant_id)
    if provider is None:
        for key in [k for k in _CACHE if k[0] == tid]:
            _CACHE.pop(key, None)
    else:
        _CACHE.pop((tid, provider), None)


def _detect_system_sa_path() -> str:
    sa_path = settings.GEMINI_SERVICE_ACCOUNT_PATH
    return sa_path if (sa_path and os.path.isfile(sa_path)) else ""


async def resolve_llm_credentials(
    db: AsyncSession, tenant_id: uuid.UUID | str, provider: str,
) -> ResolvedCredentials:
    tid = uuid.UUID(str(tenant_id)) if not isinstance(tenant_id, uuid.UUID) else tenant_id
    cache_key = (str(tid), provider)
    now = time.monotonic()
    cached = _CACHE.get(cache_key)
    if cached and cached[0] > now:
        return cached[1]

    row = (await db.execute(
        select(TenantLlmProvider).where(
            TenantLlmProvider.tenant_id == tid,
            TenantLlmProvider.provider == provider,
            TenantLlmProvider.is_enabled.is_(True),
        )
    )).scalar_one_or_none()

    resolved: ResolvedCredentials | None = None
    if row and row.api_key_encrypted:
        resolved = ResolvedCredentials(
            provider=provider, api_key=decrypt_secret(row.api_key_encrypted),
            base_url=row.base_url, extra_config=dict(row.extra_config or {}),
            service_account_path=None,
        )
    elif provider == "gemini" and tid == SYSTEM_TENANT_ID:
        sa_path = _detect_system_sa_path()
        if sa_path:
            resolved = ResolvedCredentials(
                provider="gemini", api_key="", base_url=None,
                extra_config={}, service_account_path=sa_path,
            )

    if resolved is None:
        raise ProviderNotConfiguredError(provider)

    _CACHE[cache_key] = (now + _CACHE_TTL_SECONDS, resolved)
    return resolved
```

- [ ] **Step 4: Replace `__init__.py` with the re-export version.**

```python
# backend/app/services/llm_credentials/__init__.py
"""LLM credential storage, encryption, and resolution.

Public surface:
    resolve_llm_credentials  — the single read path for provider credentials
    ResolvedCredentials      — the value object callers receive
    ProviderNotConfiguredError — raised when a tenant has no usable credential
    invalidate_cache         — drop cached creds after an admin write
"""
from app.services.llm_credentials.resolver import (
    ProviderNotConfiguredError,
    ResolvedCredentials,
    invalidate_cache,
    resolve_llm_credentials,
)

__all__ = [
    "resolve_llm_credentials", "ResolvedCredentials",
    "ProviderNotConfiguredError", "invalidate_cache",
]
```

- [ ] **Step 5: Run → PASS** (all of `test_llm_credentials_resolver.py` + `test_llm_credentials_crypto.py`).

- [ ] **Step 6: Commit.** `git add backend/app/services/llm_credentials/ backend/tests/test_llm_credentials_resolver.py && git commit -m "feat(llm-byok): resolve_llm_credentials resolver + cache"`

---

## Task 7: Rewire Sherlock — `azure_client.py` + `runtime.py`

**Files:** Modify `backend/app/services/sherlock_v3/azure_client.py` (rewrite lines 1-56; keep `supervisor_model`/`specialist_model` at 59-66), `backend/app/services/sherlock_v3/runtime.py:421-422`. Test `backend/tests/test_sherlock_azure_client.py`.

**Behaviour:** `get_sherlock_azure_client(*, tenant_id)` — **no `db` param, no `user_id`**; opens its own `async_session()` (the resolver does one SELECT — cheap). Prefer `azure_openai`, fall back to `openai`; raise `ProviderNotConfiguredError` if neither. Returns `AsyncAzureOpenAI` or `AsyncOpenAI`.

- [ ] **Step 1: Write the failing test.**

```python
# backend/tests/test_sherlock_azure_client.py
"""Sherlock requires an OpenAI-family provider; it is not a managed island."""
import openai
import pytest
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "LLM_CREDENTIAL_KEY", Fernet.generate_key().decode(), raising=False)


async def _seed(db, tenant_id, provider, api_key, base_url=None, extra=None):
    from app.models.tenant_llm_provider import TenantLlmProvider
    from app.services.llm_credentials.crypto import encrypt_secret
    db.add(TenantLlmProvider(
        tenant_id=tenant_id, provider=provider, is_enabled=True,
        api_key_encrypted=encrypt_secret(api_key), base_url=base_url, extra_config=extra or {}))
    await db.commit()


@pytest.mark.asyncio
async def test_azure_provider_yields_azure_client(db_session, seeded_tenant):
    from app.services.sherlock_v3.azure_client import get_sherlock_azure_client
    await _seed(db_session, seeded_tenant.id, "azure_openai", "az-key",
                base_url="https://x.openai.azure.com", extra={"api_version": "2025-04-01-preview"})
    client = await get_sherlock_azure_client(tenant_id=seeded_tenant.id)
    assert isinstance(client, openai.AsyncAzureOpenAI)


@pytest.mark.asyncio
async def test_openai_provider_yields_plain_client(db_session, seeded_tenant):
    from app.services.sherlock_v3.azure_client import get_sherlock_azure_client
    await _seed(db_session, seeded_tenant.id, "openai", "sk-key")
    client = await get_sherlock_azure_client(tenant_id=seeded_tenant.id)
    assert isinstance(client, openai.AsyncOpenAI) and not isinstance(client, openai.AsyncAzureOpenAI)


@pytest.mark.asyncio
async def test_no_openai_family_provider_raises(db_session, seeded_tenant):
    from app.services.llm_credentials import ProviderNotConfiguredError
    from app.services.sherlock_v3.azure_client import get_sherlock_azure_client
    await _seed(db_session, seeded_tenant.id, "anthropic", "ak-key")
    with pytest.raises(ProviderNotConfiguredError):
        await get_sherlock_azure_client(tenant_id=seeded_tenant.id)
```

> The tests seed via `db_session` but `get_sherlock_azure_client` opens its own session — both point at the same test DB, so committed rows are visible. Confirm the test DB fixture commits (not just flushes).

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Rewrite `azure_client.py` lines 1-56.**

```python
"""AsyncOpenAI / AsyncAzureOpenAI client construction for Sherlock v3.

Sherlock uses the Responses API, which both OpenAI and Azure OpenAI expose.
It is a BYOK service with a provider constraint: the tenant must have an
azure_openai OR openai provider configured. Otherwise it is locked.
"""
from __future__ import annotations

import uuid

import openai

from app.database import async_session
from app.services.llm_credentials import ProviderNotConfiguredError, resolve_llm_credentials

_DEFAULT_API_VERSION = "2025-04-01-preview"


async def get_sherlock_azure_client(*, tenant_id: uuid.UUID | str) -> openai.AsyncOpenAI:
    """Build a tenant-scoped OpenAI-family client for one Sherlock turn.

    Prefers azure_openai, falls back to openai. Raises
    ProviderNotConfiguredError if the tenant has neither.
    """
    creds = None
    async with async_session() as db:
        for provider in ("azure_openai", "openai"):
            try:
                creds = await resolve_llm_credentials(db, tenant_id, provider)
                break
            except ProviderNotConfiguredError:
                continue
    if creds is None:
        raise ProviderNotConfiguredError("openai-family (azure_openai or openai)")

    if creds.provider == "azure_openai":
        return openai.AsyncAzureOpenAI(
            api_key=creds.api_key,
            azure_endpoint=creds.base_url or "",
            api_version=creds.extra_config.get("api_version", _DEFAULT_API_VERSION),
        )
    return openai.AsyncOpenAI(api_key=creds.api_key, base_url=creds.base_url or None)
```

- [ ] **Step 4: Update the one caller — `runtime.py:421-422`.** Change:
```python
client = await get_sherlock_azure_client(tenant_id=ctx.tenant_id, user_id=ctx.user_id,)
```
to:
```python
client = await get_sherlock_azure_client(tenant_id=ctx.tenant_id)
```

- [ ] **Step 5: Run → PASS** (3 tests). Import-check: `PYTHONPATH=backend python -c "import app.services.sherlock_v3.runtime" && echo OK`.

- [ ] **Step 6: Commit.** `git add backend/app/services/sherlock_v3/azure_client.py backend/app/services/sherlock_v3/runtime.py backend/tests/test_sherlock_azure_client.py && git commit -m "feat(llm-byok): Sherlock resolves credentials via tenant_llm_providers"`

---

## Task 8: Rewire the 10 evaluator / report / job call sites

**Files (modify):** the 10 sites in the table below. (These 10 + the 3 `routes/llm.py` sites in Task 10 + the Sherlock client in Task 7 = all 14 `get_llm_settings_from_db` call sites.) Test: `backend/tests/test_inside_sales_runner_unittest.py:153`, `backend/tests/test_cost_tracking_phase3_unittest.py:50,94`.

**The transformation pattern.** Today:
```python
from app.services.evaluators.settings_helper import get_llm_settings_from_db
result = await get_llm_settings_from_db(
    tenant_id=tenant_id, user_id=user_id, auth_intent="managed_job",
    provider_override=<provider expr>)
api_key = result["api_key"]; provider = result["provider"]
selected_model = result["selected_model"]               # some sites
service_account_path = result.get("service_account_path", "")  # some sites
```
Becomes:
```python
from app.services.llm_credentials import resolve_llm_credentials
creds = await resolve_llm_credentials(db, tenant_id, <provider expr>)
api_key = creds.api_key; provider = creds.provider
service_account_path = creds.service_account_path or ""
# base_url / extra_config available as creds.base_url / creds.extra_config
```
When constructing `create_llm_provider`, always translate Azure values into the existing factory kwargs:
```python
provider_kwargs = {}
if creds.provider == "azure_openai":
    provider_kwargs["azure_endpoint"] = creds.base_url or ""
    provider_kwargs["api_version"] = creds.extra_config.get("api_version", "2025-03-01-preview")

inner = create_llm_provider(
    provider=creds.provider,
    api_key=creds.api_key,
    model_name=<explicit model source>,
    temperature=<existing temperature source>,
    service_account_path=creds.service_account_path or "",
    **provider_kwargs,
)
```

**Three rules:**
1. `<provider expr>` is now required and explicit. `selected_model` no longer comes from the credential call — repoint each `result["selected_model"]` use to the caller's own model field (`params["model"]`, `run.llm_model`, `report_run.llm_model`, etc.).
2. The resolver needs a `db: AsyncSession`. Use the per-site table below.
3. The two GAP jobs (`evaluator_draft_service`, `backfill_lead_signals_job`) read provider+model from **job params** (`params["provider"]`, `params["model"]`) — their submitters are updated in Task 9. If `params["provider"]` is absent, raise a clear `RuntimeError` — no silent default.

**Per-site table:**

| # | File:line | `<provider expr>` | Model source | `db` handling |
|---|---|---|---|---|
| 1 | `batch_runner.py:190` | existing `llm_provider`/`params` local | existing model local | open `async with async_session() as db:` around the call |
| 2 | `evaluator_draft_service.py:54` | `params["provider"]` (GAP — Task 9) | `params["model"]` | open `async with async_session() as db:` |
| 3 | `inside_sales_runner.py:373` | `llm_config.get("provider")` | existing model from `llm_config`/`params` | open `async with async_session() as db:` |
| 4 | `voice_rx_runner.py:213` | `params.get("provider")` | `params` model | open `async with async_session() as db:` (function opens others elsewhere; a dedicated one for the resolver call is fine) |
| 5 | `adversarial_runner.py:457` | `llm_provider` local | existing model local | open `async with async_session() as db:` |
| 6 | `custom_evaluator_runner.py:259` | `params.get("provider")` | `params` model | open `async with async_session() as db:` |
| 7 | `backfill_lead_signals_job.py:513` | `params["provider"]` (GAP — Task 9) | `params["model"]` | `run_backfill_lead_signals` already opens `async_session()` — pass that `db` into `_build_llm_provider` as a new parameter |
| 8 | `base_report_service.py:116` | `provider_override or run.llm_provider` | `model_override or run.llm_model` | **use `self.db`** (already in scope) |
| 9 | `report_generation_service.py:175` | `provider_override or report_run.llm_provider` | `model_override or report_run.llm_model` | add a `db: AsyncSession` param to `_create_logging_llm`; pass it from the caller at `:450` (which has `db`) |
| 10 | `eval_runner_shell.py:300` | `params.llm_config.provider` | `params.llm_config.model` | open `async with async_session() as db:` around the resolver call |

> The Sherlock client (`azure_client.py`) is the 11th service-level `get_llm_settings_from_db` site — already rewired in Task 7, not repeated here.

- [ ] **Step 1: Update the representative test.** `test_inside_sales_runner_unittest.py:153` currently patches `get_llm_settings_from_db`. Change to:
```python
from app.services.llm_credentials import ResolvedCredentials
patch("app.services.evaluators.inside_sales_runner.resolve_llm_credentials",
      new=AsyncMock(return_value=ResolvedCredentials(
          provider="gemini", api_key="test-key", base_url=None,
          extra_config={}, service_account_path=None)))
```
Also fix `test_cost_tracking_phase3_unittest.py:50,94` — change the mock path `app.services.evaluators.settings_helper.get_llm_settings_from_db` to whichever module's `resolve_llm_credentials` that test exercises, returning a `ResolvedCredentials`.

- [ ] **Step 2: Run → FAIL.** `PYTHONPATH=backend python -m pytest backend/tests/test_inside_sales_runner_unittest.py -v`.

- [ ] **Step 3: Apply the transformation to all 10 sites in the table above.** Work one file at a time; after each, import-check it.

- [ ] **Step 4: Run tests + import-check all.**
```bash
PYTHONPATH=backend python -m pytest backend/tests/test_inside_sales_runner_unittest.py backend/tests/test_cost_tracking_phase3_unittest.py -v
for m in app.services.evaluators.batch_runner app.services.evaluators.evaluator_draft_service \
  app.services.evaluators.inside_sales_runner app.services.evaluators.voice_rx_runner \
  app.services.evaluators.adversarial_runner app.services.evaluators.custom_evaluator_runner \
  app.services.evaluators.eval_runner_shell \
  app.services.analytics.backfill_lead_signals_job app.services.reports.base_report_service \
  app.services.reports.report_generation_service; do
  PYTHONPATH=backend python -c "import $m" && echo "OK $m"; done
```
Expected: tests PASS; 10 `OK`.

- [ ] **Step 5: Verify no stale refs.** `grep -rn "get_llm_settings_from_db\|settings_helper" backend/app/services` → zero hits.

- [ ] **Step 6: Commit.** `git add backend/app/services backend/tests/test_inside_sales_runner_unittest.py backend/tests/test_cost_tracking_phase3_unittest.py && git commit -m "feat(llm-byok): rewire evaluator/report/job call sites to resolve_llm_credentials"`

---

## Task 9: Submission-site provider/model injection (the 2 GAP jobs)

**Why:** `evaluator_draft_service` and `backfill_lead_signals_job` previously read provider/model from the settings default. They now read `params["provider"]`/`params["model"]` (Task 8). Their submitters must put those values in the job params — explicit, never defaulted.

**Files:**
- Modify `backend/app/routes/analytics_admin.py:593-605,649-663` (`backfill-lead-signals` submitter)
- Modify `src/features/*/components/CreateEvaluatorWizard.tsx` (`generate-evaluator-draft` submitter — the **one bridging frontend edit** in this phase)
- Verify `backend/app/routes/jobs.py:89-126` passes `params` through unchanged (generic submission — no edit expected, just confirm)

- [ ] **Step 1: `backfill-lead-signals` — backend admin endpoint.** In `analytics_admin.py`, add `provider: str` and `model: str` to the request body schema for the backfill endpoint (required fields). In the params dict built at `:593-605`, include `"provider": body.provider, "model": body.model`. If a frontend admin trigger for this exists, grep for it (`grep -rn "backfill-lead-signals" src/`) and add a provider/model picker there too; if none exists (admin-only API trigger), document that the caller must supply them.

- [ ] **Step 2: `generate-evaluator-draft` — the wizard.** Read `CreateEvaluatorWizard.tsx` fully (it has `modelId` state at `:119`, submits the draft job at `~:361`). Add `provider` and `model` to the `submitAndPollJob('generate-evaluator-draft', { ... })` params object. Source them from the wizard's existing state — it already tracks `modelId`; find its provider state (or the `appConfig.evaluator` default provider) and pass both. The wizard's existing `LLMConfigSection` (still the old version in Phase 1) keeps working — its prop contract is preserved through the Phase 3 rewrite.

- [ ] **Step 3: Confirm the generic path.** Read `routes/jobs.py:89-126` — confirm `provider`/`model` in the request `params` survive into the `BackgroundJob.params` dict (it injects `tenant_id`/`user_id` and otherwise passes through). No edit expected.

- [ ] **Step 4: Verify.** Backend: `PYTHONPATH=backend python -c "import app.routes.analytics_admin" && echo OK`. Frontend: `npm run lint && npx tsc -b`.

- [ ] **Step 5: Commit.** `git add backend/app/routes/analytics_admin.py src/features && git commit -m "feat(llm-byok): submission sites inject provider/model into job params"`

---

## Task 10: Rewire the 3 `routes/llm.py` call sites

**Files:** Modify `backend/app/routes/llm.py:105-109,235-239,315-319` (helpers `_discover_azure_openai_models`, `_discover_gemini_models`, `_get_provider_key_from_db`).

> These 3 are inside **helper functions**, not route handlers — no `db` in scope. Each opens its own `async with async_session() as db:`. The fuller `routes/llm.py` rewrite (auth-status, discovery extraction) is Phase 2 — here, just the minimal rewire so the file imports and the routes still answer.

- [ ] **Step 1: Apply the transformation.** Replace each `get_llm_settings_from_db(...)` with `resolve_llm_credentials(db, <tenant_id>, <provider>)` inside a `async with async_session() as db:`. Rewrite `_get_provider_key_from_db` to:
```python
async def _get_provider_key_from_db(tenant_id, provider: str) -> str:
    from app.database import async_session
    from app.services.llm_credentials import ProviderNotConfiguredError, resolve_llm_credentials
    try:
        async with async_session() as db:
            creds = await resolve_llm_credentials(db, tenant_id, provider)
        return creds.api_key
    except ProviderNotConfiguredError:
        return ""
```
Update its callers to pass `tenant_id` (from `auth.tenant_id`) instead of `auth`.

- [ ] **Step 2: Import-check.** `PYTHONPATH=backend python -c "import app.routes.llm" && echo OK`.

- [ ] **Step 3: Verify global clean.** `grep -rn "get_llm_settings_from_db\|settings_helper" backend/app` → zero hits.

- [ ] **Step 4: Commit.** `git add backend/app/routes/llm.py && git commit -m "feat(llm-byok): rewire routes/llm.py call sites to resolve_llm_credentials"`

---

## Task 11: Delete `settings_helper.py`

- [ ] **Step 1: Confirm zero references.** `grep -rn "settings_helper\|get_llm_settings_from_db" backend/` → zero hits.
- [ ] **Step 2: Delete.** `git rm backend/app/services/evaluators/settings_helper.py`
- [ ] **Step 3: Smoke test.** `PYTHONPATH=backend python -c "import app.main" && echo OK`.
- [ ] **Step 4: Commit.** `git commit -m "feat(llm-byok): delete settings_helper.py — superseded by resolve_llm_credentials"`

---

## Task 12: Remove tenant LLM env fallbacks + fix `chat_engine.py`

**Files:** Modify `backend/app/config.py:19-33`, `backend/app/routes/chat_engine.py:13-20`. Test `backend/tests/test_no_dead_llm_env_vars.py`.

- [ ] **Step 1: Write the failing test.**

```python
# backend/tests/test_no_dead_llm_env_vars.py
"""Tenant LLM provider env fallbacks must be gone; system SA survivor stays."""
REMOVED = [
    "GEMINI_API_KEY", "GEMINI_AUTH_METHOD", "GEMINI_MODEL", "OPENAI_API_KEY",
    "OPENAI_MODEL", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_VERSION", "AZURE_OPENAI_MODEL", "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL", "DEFAULT_LLM_PROVIDER", "EVAL_TEMPERATURE",
]
KEPT = ["GEMINI_SERVICE_ACCOUNT_PATH", "LLM_CREDENTIAL_KEY", "ORCHESTRATION_CONNECTION_KEY"]


def test_removed_vars_absent():
    from app.config import Settings
    fields = set(Settings.model_fields.keys())
    for name in REMOVED:
        assert name not in fields, f"{name} should have been removed"


def test_kept_vars_present():
    from app.config import Settings
    fields = set(Settings.model_fields.keys())
    for name in KEPT:
        assert name in fields, f"{name} must remain"
```

- [ ] **Step 2: Run → FAIL** (`test_removed_vars_absent`).

- [ ] **Step 3: Edit `config.py`.** Replace lines 19-33 (the `# LLM providers ...` block through `EVAL_TEMPERATURE`) with just the SA survivor:
```python
    # Gemini service account — system-tenant-only fallback for Sherlock/Gemini.
    # Decoded from GEMINI_SERVICE_ACCOUNT_JSON to a file by entrypoint.sh in prod.
    # Planned-deprecation: full removal + per-tenant SA upload tracked separately.
    GEMINI_SERVICE_ACCOUNT_PATH: str = ""
```
(`LLM_CREDENTIAL_KEY` already added in Task 1. `SHERLOCK_SUPERVISOR_MODEL`/`SHERLOCK_SPECIALIST_MODEL` are read via `os.getenv` in `azure_client.py`, not declared here — leave them.)

- [ ] **Step 4: Fix `chat_engine.py:18`.** Replace `os.getenv("OPENAI_MODEL", "") or "gpt-5.4"` with `"gpt-5.4"`. Remove `import os` if now unused (`grep -n "os\." backend/app/routes/chat_engine.py`).

- [ ] **Step 5: Run + smoke.** `PYTHONPATH=backend python -m pytest backend/tests/test_no_dead_llm_env_vars.py -v` (PASS); `PYTHONPATH=backend python -c "import app.routes.chat_engine; import app.main" && echo OK`.

- [ ] **Step 6: Commit.** `git add backend/app/config.py backend/app/routes/chat_engine.py backend/tests/test_no_dead_llm_env_vars.py && git commit -m "feat(llm-byok): remove tenant LLM env fallbacks"`

---

## Task 13: Deploy-config cleanup + registries + full suite

**Files:** `docker-compose.prod.yml`, `docker-compose.yml`, `.env.backend` example, `docs/SETUP.md`, `docs/devops-handover.md`, `CLAUDE.md`, `.github/copilot-instructions.md`.

- [ ] **Step 1: Compose + env files.** Delete the tenant provider key/model pass-through lines from `docker-compose.prod.yml` (~46-61) and `docker-compose.yml`: `GEMINI_API_KEY`, `GEMINI_AUTH_METHOD`, `GEMINI_MODEL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_VERSION`, `AZURE_OPENAI_MODEL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `DEFAULT_LLM_PROVIDER`, `EVAL_TEMPERATURE`. **Keep** `GEMINI_SERVICE_ACCOUNT_PATH`, `GEMINI_SERVICE_ACCOUNT_JSON`, the `service-account.json` volume mount, and `entrypoint.sh`. Add `LLM_CREDENTIAL_KEY: ${LLM_CREDENTIAL_KEY:-}` next to `ORCHESTRATION_CONNECTION_KEY`. Add `LLM_CREDENTIAL_KEY=` to `.env.backend` with the Fernet-generate comment.

- [ ] **Step 2: Docs.** In `docs/SETUP.md` + `docs/devops-handover.md`: remove the tenant provider key/model vars from the provider tables; add an `LLM_CREDENTIAL_KEY` row (Required); add a note that provider keys are configured per-tenant in **Admin → AI Settings** (Phase 2), not env vars; annotate `GEMINI_SERVICE_ACCOUNT_*` as "system tenant only, planned-deprecation". **Flag the deploy prerequisite:** `LLM_CREDENTIAL_KEY` must be set before the Phase-1 image deploys (migration 0047 backfill needs it).

- [ ] **Step 3: Registries.** In `CLAUDE.md`: ORM tables count 77 → 78, append `platform.tenant_llm_providers`; in "Backend Lifespan Boot Order" step 2, add `LLM_CREDENTIAL_KEY` to the boot-validated vars. Mirror to `.github/copilot-instructions.md` if it carries the table list.

- [ ] **Step 4: Compose parses.** `docker compose -f docker-compose.prod.yml config >/dev/null && docker compose config >/dev/null && echo OK`.

- [ ] **Step 5: Full backend suite.** `pyenv activate venv-python-ai-evals-arize && PYTHONPATH=backend python -m pytest backend/tests/ -q` — all green. Fix any failure (common fallout: a test importing `settings_helper` or a removed env var). Do not skip.

- [ ] **Step 6: Boot end-to-end.** `cd backend && alembic upgrade head && cd .. && PYTHONPATH=backend python -m uvicorn app.main:app --port 8721` — boots past `_validate_startup_config` and lifespan with no `RuntimeError`/`ImportError`. Ctrl-C.

- [ ] **Step 7: Commit.** `git add docker-compose.prod.yml docker-compose.yml .env.backend docs/SETUP.md docs/devops-handover.md CLAUDE.md .github/copilot-instructions.md && git commit -m "chore(llm-byok): deploy config cleanup + registry updates"`

---

## Phase 1 Done — Verification Checklist ✅

All gates green as of branch head `9252a76` (2026-05-16):

- [x] `grep -rn "get_llm_settings_from_db\|settings_helper" backend/` → zero hits
- [x] `grep -rn "GEMINI_API_KEY\|OPENAI_API_KEY\|ANTHROPIC_API_KEY\|AZURE_OPENAI_API_KEY\|DEFAULT_LLM_PROVIDER\|EVAL_TEMPERATURE" backend/app/` → zero hits
- [x] `grep -rn "GEMINI_SERVICE_ACCOUNT_PATH" backend/app/` → 3 hits: `config.py`, `llm_credentials/resolver.py`, `routes/llm.py` `auth_status` (Phase-1 inline SA check; Phase 2's broader `auth-status` rewrite leaves this surface as-is)
- [x] `alembic upgrade head` clean on shared dev DB; `alembic downgrade -1` then `upgrade head` clean
- [x] Full backend pytest suite — 0 new failures introduced (49 pre-existing failures unchanged; verified by stash-diff before/after)
- [x] Backend boots end-to-end via uvicorn; lifespan validator raises clear `RuntimeError` when `LLM_CREDENTIAL_KEY` is missing or invalid Fernet
- [x] Old `application_settings` `llm-settings` rows still present (preserved for Phase 3 / migration 0048 rollback window)
- [x] `npm run lint && npx tsc -b` introduce 0 new failures (97 problems pre/post identical; tsc clean)
- [x] All 14 Phase 1 commits are on `feat/llm-credentials-cleanup`; the branch builds and boots; NOT merged to `main`

**Plan-vs-reality deltas accepted into Phase 1:**

- Live call-site count was **13, not 14** — `inside_sales_runner.py` was already consolidated into `eval_runner_shell.py` before this branch started, so Task 8's site #3 had nothing to rewire. The remaining 9 evaluator/report/job sites + 3 `routes/llm.py` helpers + Sherlock client = 13 live rewires.
- `auth-status` had to do its own `tenant_llm_providers` query in Phase 1 (Task 12) because the env-var fallbacks it relied on were being removed. Phase 2's plan-described `auth-status` rewrite should treat this as already done and focus on the `routes/llm.py` discovery extraction.
- Sherlock specialist + supervisor type signatures widened from `AsyncAzureOpenAI` → `AsyncOpenAI` in 4 files so the resolver's fallback to plain `openai` actually type-checks downstream.
- `_create_logging_llm` (report_generation_service.py) gained `db`, `run_provider`, `run_model` parameters; both callers updated.
- `generate_evaluator_draft` gained required `provider`, `model` parameters; the job handler injects them from `params`.
- `BackfillRequest` gained required `provider`, `model` fields; `parse_request` validates; admin endpoint schema (`BackfillLeadSignalsRequest`) requires them.
- Test fixture pattern: live-DB tests for code paths that open their own `async_session()` must mock the session factory because conftest's outer-transaction-plus-savepoint isolation hides commits from other connections. See `_patch_async_session` in `backend/tests/test_sherlock_azure_client.py`.
- Post-audit cleanups (`9252a76`): `TenantLlmProvider.is_enabled` gained `server_default=false()` to mirror migration DDL; `docker-compose.yml` got explicit `LLM_CREDENTIAL_KEY` pass-through; `_discover_azure_openai_models` docstring fixed to drop dead `AZURE_OPENAI_MODEL` reference.

**Phase 2 deploy prerequisite (re-stated for clarity):** generate a Fernet key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and set it as a Container Apps **secret** (not `value:`) via `secretref:` before the Phase-1 image deploys. `entrypoint.sh` runs `alembic upgrade head` on boot and migration 0047's backfill calls `encrypt_secret` — boot fails fast if the key is missing or invalid Fernet.
