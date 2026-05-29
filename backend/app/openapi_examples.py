"""Helpers for concise OpenAPI response documentation (example bodies + descriptions)."""
from typing import Any


def ok(description: str, example: Any) -> dict:
    """A success-response entry carrying a concrete example body."""
    return {"description": description, "content": {"application/json": {"example": example}}}


def err(description: str, detail: str) -> dict:
    """An error-response entry carrying a concrete ``{"detail": ...}`` example body."""
    return {"description": description, "content": {"application/json": {"example": {"detail": detail}}}}
