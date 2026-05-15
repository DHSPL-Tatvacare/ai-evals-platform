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
