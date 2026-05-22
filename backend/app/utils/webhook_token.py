"""Shared webhook-token generator for both webhook families (connections + triggers)."""
from __future__ import annotations

import secrets


def generate_webhook_token() -> str:
    """32-byte urlsafe token (~43 chars), inside the VARCHAR(64) column.

    ~256 bits of entropy keeps collision probability astronomically below the
    partial-unique index's enforcement bar."""
    return secrets.token_urlsafe(32)


__all__ = ["generate_webhook_token"]
