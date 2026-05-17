"""LLM credential storage, encryption, and resolution.

Public surface:
    resolve_credentials      — the single read path for provider credentials
    ResolvedCredentials      — credential value object (dict ``secret``)
    ProviderNotConfiguredError — raised when a tenant has no usable credential
    invalidate_cache         — drop cached creds after an admin write

Call-site abstraction (Phase 2):
    resolve_llm_call         — "what model/cred for this call site?"
    ResolvedLlmCall          — call-site value object (creds + model + caps)
    CallSiteNotConfiguredError / CallSiteCapabilityMismatch / CallSiteCapabilityUnknown
    invalidate_call_site_cache
    CALL_SITES / get_call_site / list_call_sites / UnknownCallSiteError
    compute_capabilities

Low-level crypto:
    encrypt_json/decrypt_json — runtime crypto for ``secret_blob_encrypted``
    encrypt_secret/decrypt_secret — legacy single-string crypto, kept ONLY for
        migrations 0047 + 0050 backfill paths (do not import from runtime code).
"""
from app.services.llm_credentials.call_site_resolver import (
    CallSiteCapabilityMismatch,
    CallSiteCapabilityUnknown,
    CallSiteNotConfiguredError,
    ResolvedLlmCall,
    invalidate_call_site_cache,
    resolve_llm_call,
)
from app.services.llm_credentials.call_sites import (
    CALL_SITES,
    CallSiteSpec,
    UnknownCallSiteError,
    get_call_site,
    list_call_sites,
)
from app.services.llm_credentials.capabilities import compute_capabilities
from app.services.llm_credentials.crypto import (
    decrypt_json,
    decrypt_secret,
    encrypt_json,
    encrypt_secret,
)
from app.services.llm_credentials.resolver import (
    ProviderNotConfiguredError,
    ResolvedCredentials,
    invalidate_cache,
    resolve_credentials,
)

__all__ = [
    "resolve_credentials",
    "ResolvedCredentials",
    "ProviderNotConfiguredError",
    "invalidate_cache",
    "resolve_llm_call",
    "ResolvedLlmCall",
    "CallSiteNotConfiguredError",
    "CallSiteCapabilityMismatch",
    "CallSiteCapabilityUnknown",
    "invalidate_call_site_cache",
    "CALL_SITES",
    "CallSiteSpec",
    "UnknownCallSiteError",
    "get_call_site",
    "list_call_sites",
    "compute_capabilities",
    "encrypt_json",
    "decrypt_json",
    "encrypt_secret",
    "decrypt_secret",
]
