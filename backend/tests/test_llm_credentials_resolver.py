"""resolve_llm_credentials: enabled tenant row -> system-tenant SA -> ProviderNotConfiguredError."""
import uuid

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "LLM_CREDENTIAL_KEY", Fernet.generate_key().decode(), raising=False)


@pytest_asyncio.fixture
async def seeded_tenant(db_session):
    """Create a fresh tenant row so tenant_llm_providers FK targets exist."""
    from app.models.tenant import Tenant
    tenant = Tenant(
        id=uuid.uuid4(),
        name="llm-byok-test-tenant",
        slug=f"llm-byok-test-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(tenant)
    await db_session.commit()
    return tenant


@pytest.fixture(autouse=True)
def _clear_resolver_cache():
    from app.services.llm_credentials.resolver import _CACHE
    _CACHE.clear()
    yield
    _CACHE.clear()


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
    sa = tmp_path / "sa.json"
    sa.write_text("{}")
    monkeypatch.setattr(settings, "GEMINI_SERVICE_ACCOUNT_PATH", str(sa))
    from app.services.llm_credentials import resolve_llm_credentials
    creds = await resolve_llm_credentials(db_session, SYSTEM_TENANT_ID, "gemini")
    assert creds.service_account_path == str(sa) and creds.api_key == ""


@pytest.mark.asyncio
async def test_real_tenant_gemini_never_uses_env_sa(db_session, seeded_tenant, monkeypatch, tmp_path):
    from app.config import settings
    from app.services.llm_credentials import ProviderNotConfiguredError, resolve_llm_credentials
    sa = tmp_path / "sa.json"
    sa.write_text("{}")
    monkeypatch.setattr(settings, "GEMINI_SERVICE_ACCOUNT_PATH", str(sa))
    with pytest.raises(ProviderNotConfiguredError):
        await resolve_llm_credentials(db_session, seeded_tenant.id, "gemini")
