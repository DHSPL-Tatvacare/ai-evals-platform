"""Scope resolver authorization tests for orchestration analytics."""

import uuid
from types import SimpleNamespace

import pytest

from app.services.orchestration.analytics.scope import (
    ScopeForbidden,
    resolve_analytics_scope,
)


def _auth(perms, owner=False):
    return SimpleNamespace(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        is_owner=owner,
        permissions=frozenset(perms),
        app_access=frozenset({"x"}),
    )


def test_plain_user_mine_ok():
    assert resolve_analytics_scope(_auth({"orchestration:manage"}), "mine") is not None


def test_plain_user_tenant_forbidden():
    with pytest.raises(ScopeForbidden):
        resolve_analytics_scope(_auth({"orchestration:manage"}), "tenant")


def test_admin_tenant_ok():
    assert resolve_analytics_scope(_auth({"cost:view"}), "tenant") is not None


def test_owner_tenant_ok():
    assert resolve_analytics_scope(_auth(set(), owner=True), "tenant") is not None
