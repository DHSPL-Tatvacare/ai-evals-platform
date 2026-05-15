"""Live model discovery against resolved tenant credentials.

Single entry point:

    list_models_for_provider(provider, creds) -> list[str]

The caller resolves credentials first; this module never reads env vars.
Raises ``ValueError`` on credential / auth failures (caller maps to
``validation_status='invalid'``). Other errors (network, transient SDK
failures) propagate so unexpected bugs surface instead of being swallowed.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Sequence

from app.services.llm_credentials import ResolvedCredentials


logger = logging.getLogger(__name__)


def _dedupe_preserving_order(names: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


async def list_models_for_provider(
    provider: str, creds: ResolvedCredentials
) -> list[str]:
    """Return the live model id list for one provider.

    - ``openai`` / ``anthropic``: hit the provider SDK ``models.list`` API.
    - ``azure_openai``: deployments are admin-configured on the tenant row;
      surface ``extra_config["deployments"]`` directly (Azure has no public
      key-based listing).
    - ``gemini``: Vertex AI (system-tenant SA) or API key; both via the
      ``google.genai`` client.
    """
    if provider == "openai":
        return await _list_openai(creds)
    if provider == "azure_openai":
        return _list_azure(creds)
    if provider == "anthropic":
        return await _list_anthropic(creds)
    if provider == "gemini":
        return await _list_gemini(creds)
    raise ValueError(f"Unsupported provider for model discovery: {provider}")


async def _list_openai(creds: ResolvedCredentials) -> list[str]:
    if not creds.api_key:
        raise ValueError("OpenAI API key not configured")
    try:
        import openai
    except ImportError as exc:
        raise ValueError(f"openai SDK unavailable: {exc}") from exc
    client = openai.OpenAI(api_key=creds.api_key, base_url=creds.base_url or None)
    try:
        raw = await asyncio.to_thread(lambda: list(client.models.list()))
    except openai.AuthenticationError as exc:
        raise ValueError(f"OpenAI authentication failed: {exc}") from exc
    except openai.PermissionDeniedError as exc:
        raise ValueError(f"OpenAI permission denied: {exc}") from exc
    names = [m.id for m in raw if getattr(m, "id", None)]
    names.sort()
    return _dedupe_preserving_order(names)


def _list_azure(creds: ResolvedCredentials) -> list[str]:
    """Azure has no public key-based deployment listing; admins curate by hand.

    We return the admin-curated list from ``extra_config["deployments"]``.
    Credential validity is verified separately by ``validate_azure_credentials``
    so the validate route doesn't pass with an empty deployment list.
    """
    raw = creds.extra_config.get("deployments") or []
    if isinstance(raw, str):
        # Tolerate legacy CSV/newline strings; new admin writes a list.
        names = [chunk.strip() for chunk in raw.replace("\n", ",").split(",") if chunk.strip()]
    elif isinstance(raw, list):
        names = [str(n).strip() for n in raw if str(n).strip()]
    else:
        names = []
    return _dedupe_preserving_order(names)


async def validate_azure_credentials(creds: ResolvedCredentials) -> None:
    """Hit the Azure resource with the saved key + endpoint + api_version.

    Uses ``client.models.list()``, which the Azure data-plane exposes at
    ``GET /openai/models?api-version=...`` for key-authenticated callers.
    A 401/403 surfaces as ``ValueError`` so the validate route can mark the
    row ``invalid``; other failures propagate so unexpected bugs aren't
    swallowed.
    """
    if not creds.api_key:
        raise ValueError("Azure OpenAI API key not configured")
    if not creds.base_url:
        raise ValueError("Azure OpenAI endpoint not configured")
    try:
        import openai
    except ImportError as exc:
        raise ValueError(f"openai SDK unavailable: {exc}") from exc
    client = openai.AzureOpenAI(
        api_key=creds.api_key,
        azure_endpoint=creds.base_url,
        api_version=creds.extra_config.get("api_version") or "2025-04-01-preview",
    )
    try:
        await asyncio.to_thread(lambda: list(client.models.list()))
    except openai.AuthenticationError as exc:
        raise ValueError(f"Azure OpenAI authentication failed: {exc}") from exc
    except openai.PermissionDeniedError as exc:
        raise ValueError(f"Azure OpenAI permission denied: {exc}") from exc
    except openai.NotFoundError as exc:
        # Wrong endpoint or wrong api_version comes back as 404.
        raise ValueError(f"Azure OpenAI endpoint/api-version invalid: {exc}") from exc


async def _list_anthropic(creds: ResolvedCredentials) -> list[str]:
    if not creds.api_key:
        raise ValueError("Anthropic API key not configured")
    try:
        import anthropic
    except ImportError as exc:
        raise ValueError(f"anthropic SDK unavailable: {exc}") from exc
    client = anthropic.Anthropic(api_key=creds.api_key)
    try:
        raw = await asyncio.to_thread(lambda: list(client.models.list()))
    except anthropic.AuthenticationError as exc:
        raise ValueError(f"Anthropic authentication failed: {exc}") from exc
    except anthropic.PermissionDeniedError as exc:
        raise ValueError(f"Anthropic permission denied: {exc}") from exc
    names = [m.id for m in raw if getattr(m, "id", None)]
    names.sort()
    return _dedupe_preserving_order(names)


async def _list_gemini(creds: ResolvedCredentials) -> list[str]:
    try:
        from google import genai
    except ImportError as exc:
        raise ValueError(f"google-genai SDK unavailable: {exc}") from exc

    sa_path = creds.service_account_path or ""
    if sa_path and os.path.isfile(sa_path):
        import json as _json

        from google.oauth2 import service_account

        with open(sa_path) as f:
            sa_info = _json.load(f)
        project_id = sa_info.get("project_id", "")
        sa_creds = service_account.Credentials.from_service_account_file(
            sa_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        client = genai.Client(vertexai=True, project=project_id, credentials=sa_creds)
    elif creds.api_key:
        client = genai.Client(api_key=creds.api_key)
    else:
        raise ValueError("Gemini credentials missing: no API key and no service account")

    def _collect() -> list[str]:
        names: list[str] = []
        for model in client.models.list():
            name = getattr(model, "name", None) or ""
            if not name or "gemini" not in name or "embedding" in name:
                continue
            for prefix in (
                "publishers/google/models/",
                "publishers/google/",
                "models/",
            ):
                if name.startswith(prefix):
                    name = name[len(prefix):]
                    break
            names.append(name)
        names.sort()
        return names

    return _dedupe_preserving_order(await asyncio.to_thread(_collect))
