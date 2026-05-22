"""Shared webhook-token generator — one generator for both webhook families."""
from __future__ import annotations


def test_generate_webhook_token_urlsafe_and_unique():
    from app.utils.webhook_token import generate_webhook_token

    a = generate_webhook_token()
    b = generate_webhook_token()
    assert a != b
    # token_urlsafe(32) → ~43 chars, inside the VARCHAR(64) column.
    assert 0 < len(a) <= 64
    assert all(c.isalnum() or c in "-_" for c in a)


def test_connections_service_reuses_shared_generator():
    # The connections service must delegate to the shared util (no second generator).
    from app.services.orchestration.api import connections
    from app.utils.webhook_token import generate_webhook_token

    assert connections._generate_webhook_token is generate_webhook_token
