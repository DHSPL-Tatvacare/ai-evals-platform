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
