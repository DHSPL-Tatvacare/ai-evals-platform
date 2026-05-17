"""Sherlock client + model resolution — Phase 2 call-site driven.

Phase 2 (2026-05-18) replaced the env-var-backed ``supervisor_model()`` /
``specialist_model()`` helpers and the ``_DEFAULT_API_VERSION`` constant with
a single call-site-driven helper:

    get_sherlock_azure_client(*, tenant_id, call_site) -> (client, model)

Tests cover:
- Azure-credential tenant → AsyncAzureOpenAI client + the deployment name
  resolved through the analytics_supervisor / analytics_specialist call sites
- OpenAI-only tenant falls through to platform default → AsyncOpenAI client
  + the canonical model id
- No credential of any OpenAI-family provider raises CallSiteNotConfigured /
  ProviderNotConfigured
"""
import uuid
from contextlib import asynccontextmanager

import openai
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "LLM_CREDENTIAL_KEY", Fernet.generate_key().decode(), raising=False)


@pytest.fixture(autouse=True)
def _clear_caches():
    from app.services.llm_credentials.call_site_resolver import _CACHE as cc
    from app.services.llm_credentials.resolver import _CACHE as creds_cache
    cc.clear()
    creds_cache.clear()
    yield
    cc.clear()
    creds_cache.clear()


@pytest.fixture
def _patch_async_session(monkeypatch, db_session):
    """Reroute azure_client.async_session() to yield the live db_session."""
    @asynccontextmanager
    async def _yield_test_session():
        yield db_session

    monkeypatch.setattr(
        "app.services.sherlock_v3.azure_client.async_session",
        _yield_test_session,
    )


@pytest_asyncio.fixture
async def seeded_tenant(db_session):
    from app.models.tenant import Tenant
    tenant = Tenant(
        id=uuid.uuid4(),
        name="sherlock-test-tenant",
        slug=f"sherlock-test-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(tenant)
    await db_session.commit()
    return tenant


@pytest_asyncio.fixture
async def gpt5_catalog(db_session):
    """Seed a canonical OpenAI gpt-5 catalog row + supervisor/specialist tags."""
    from app.models.cost import RefLlmModelsCatalog
    rows = [
        RefLlmModelsCatalog(
            provider_key="openai", provider="openai",
            model_id="gpt-5", model="gpt-5", display_name="GPT-5",
            modalities_input=["text"], modalities_output=["text"],
            supports_tool_call=True, supports_structured_output=True,
        ),
        RefLlmModelsCatalog(
            provider_key="openai", provider="openai",
            model_id="gpt-5-mini", model="gpt-5-mini", display_name="GPT-5 mini",
            modalities_input=["text"], modalities_output=["text"],
            supports_tool_call=True, supports_structured_output=True,
        ),
    ]
    for r in rows:
        db_session.add(r)
    await db_session.commit()
    return rows


async def _seed_credential(db, tenant_id, provider, api_key, *, extra=None):
    from app.models.tenant_llm_credential import TenantLlmCredential
    from app.services.llm_credentials.crypto import encrypt_json
    cred = TenantLlmCredential(
        tenant_id=tenant_id, provider=provider, name="default", is_enabled=True,
        secret_blob_encrypted=encrypt_json({"api_key": api_key}),
        extra_config=extra or {},
    )
    db.add(cred)
    await db.commit()
    return cred


async def _seed_platform_default(db, call_site, provider, model):
    from app.models.tenant_call_site_default import TenantCallSiteDefault
    db.add(
        TenantCallSiteDefault(
            tenant_id=None,
            call_site=call_site,
            provider=provider,
            credential_name="default",
            model_or_deployment=model,
        )
    )
    await db.commit()


async def _seed_tenant_azure_default(db, tenant_id, call_site, deployment_name):
    from app.models.tenant_call_site_default import TenantCallSiteDefault
    db.add(
        TenantCallSiteDefault(
            tenant_id=tenant_id,
            call_site=call_site,
            provider="azure_openai",
            credential_name="default",
            model_or_deployment=deployment_name,
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_unknown_call_site_raises(db_session, seeded_tenant, _patch_async_session):
    from app.services.llm_credentials import UnknownCallSiteError
    from app.services.sherlock_v3.azure_client import get_sherlock_azure_client
    with pytest.raises(UnknownCallSiteError):
        await get_sherlock_azure_client(
            tenant_id=seeded_tenant.id, call_site="not_a_real_site",
        )


@pytest.mark.asyncio
async def test_openai_platform_default_yields_async_openai_client(
    db_session, seeded_tenant, gpt5_catalog, _patch_async_session
):
    """OpenAI-only tenant + platform-default rows → AsyncOpenAI client."""
    _ = gpt5_catalog
    await _seed_credential(db_session, seeded_tenant.id, "openai", "sk-test")
    await _seed_platform_default(db_session, "analytics_supervisor", "openai", "gpt-5")
    await _seed_platform_default(db_session, "analytics_specialist", "openai", "gpt-5-mini")

    from app.services.sherlock_v3.azure_client import get_sherlock_azure_client

    sup_client, sup_model = await get_sherlock_azure_client(
        tenant_id=seeded_tenant.id, call_site="analytics_supervisor",
    )
    assert isinstance(sup_client, openai.AsyncOpenAI)
    assert not isinstance(sup_client, openai.AsyncAzureOpenAI)
    assert sup_model == "gpt-5"

    spec_client, spec_model = await get_sherlock_azure_client(
        tenant_id=seeded_tenant.id, call_site="analytics_specialist",
    )
    assert isinstance(spec_client, openai.AsyncOpenAI)
    assert spec_model == "gpt-5-mini"


@pytest.mark.asyncio
async def test_azure_tenant_row_yields_azure_client_and_deployment_name(
    db_session, seeded_tenant, gpt5_catalog, _patch_async_session
):
    """Azure tenant row preserved by migration 0051 → AsyncAzureOpenAI client +
    the tenant-chosen deployment string."""
    from app.models.tenant_llm_deployment import TenantLlmDeployment
    cred = await _seed_credential(
        db_session, seeded_tenant.id, "azure_openai", "az-key",
        extra={"base_url": "https://x.openai.azure.com", "api_version": "2025-04-01-preview"},
    )
    db_session.add(
        TenantLlmDeployment(
            credential_id=cred.id,
            deployment_name="my-sherlock-gpt5",
            canonical_model_id=gpt5_catalog[0].id,
            needs_mapping=False,
            enabled=True,
        )
    )
    await db_session.commit()
    await _seed_tenant_azure_default(
        db_session, seeded_tenant.id, "analytics_supervisor", "my-sherlock-gpt5",
    )

    from app.services.sherlock_v3.azure_client import get_sherlock_azure_client

    client, model = await get_sherlock_azure_client(
        tenant_id=seeded_tenant.id, call_site="analytics_supervisor",
    )
    assert isinstance(client, openai.AsyncAzureOpenAI)
    assert model == "my-sherlock-gpt5"


@pytest.mark.asyncio
async def test_no_default_raises_call_site_not_configured(
    db_session, seeded_tenant, _patch_async_session
):
    """No tenant default and no platform default for analytics_supervisor →
    CallSiteNotConfiguredError (no fallback to env vars)."""
    from app.services.llm_credentials import CallSiteNotConfiguredError
    from app.services.sherlock_v3.azure_client import get_sherlock_azure_client
    await _seed_credential(db_session, seeded_tenant.id, "anthropic", "ak-key")
    with pytest.raises(CallSiteNotConfiguredError):
        await get_sherlock_azure_client(
            tenant_id=seeded_tenant.id, call_site="analytics_supervisor",
        )


@pytest.mark.asyncio
async def test_non_openai_family_provider_resolution_raises(
    db_session, seeded_tenant, _patch_async_session
):
    """If a platform default somehow points at a non-OpenAI-family provider
    (e.g. anthropic) for a Sherlock call site, the azure_client's
    ``else: raise`` branch fires — Sherlock's Responses API surface can't
    talk to Anthropic directly, so we refuse loudly instead of silently
    constructing a useless client."""
    from app.models.cost import RefLlmModelsCatalog
    from app.services.llm_credentials import CallSiteNotConfiguredError
    from app.services.sherlock_v3.azure_client import get_sherlock_azure_client

    # Seed an Anthropic catalog row that satisfies analytics_supervisor's
    # required caps (text_input + text_output + tool_call).
    cat = RefLlmModelsCatalog(
        provider_key="anthropic", provider="anthropic",
        model_id="claude-sonnet-4-5", model="claude-sonnet-4-5",
        display_name="Claude Sonnet 4.5",
        modalities_input=["text"], modalities_output=["text"],
        supports_tool_call=True, supports_structured_output=False,
    )
    db_session.add(cat)
    await _seed_credential(db_session, seeded_tenant.id, "anthropic", "ak-key")
    await _seed_platform_default(
        db_session, "analytics_supervisor", "anthropic", "claude-sonnet-4-5",
    )
    with pytest.raises(CallSiteNotConfiguredError) as excinfo:
        await get_sherlock_azure_client(
            tenant_id=seeded_tenant.id, call_site="analytics_supervisor",
        )
    assert "OpenAI Responses API" in str(excinfo.value)
