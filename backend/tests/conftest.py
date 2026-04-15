"""Shared pytest fixtures for backend tests."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, Mock

import pytest

from app.auth import AuthContext


# ── Auth fixtures ──────────────────────────────────────────────

@pytest.fixture
def tenant_id():
    return uuid.uuid4()


@pytest.fixture
def user_id():
    return uuid.uuid4()


@pytest.fixture
def auth(tenant_id, user_id):
    """Standard auth context with owner privileges and all app access."""
    return AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        email='test@example.com',
        role_id=uuid.uuid4(),
        is_owner=True,
        permissions=frozenset(),
        app_access=frozenset({'voice-rx', 'kaira-bot', 'inside-sales'}),
    )


@pytest.fixture
def auth_for_app():
    """Factory: auth context scoped to specific apps."""
    def _make(*app_ids: str, is_owner: bool = False):
        return AuthContext(
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            email='test@example.com',
            role_id=uuid.uuid4(),
            is_owner=is_owner,
            permissions=frozenset(),
            app_access=frozenset(app_ids),
        )
    return _make


# ── Database fixtures ──────────────────────────────────────────

class FakeResult:
    """Simulates SQLAlchemy result objects."""
    def __init__(self, *, rows=None, scalar_value=None, first_row=None):
        self._rows = rows or []
        self._scalar_value = scalar_value
        self._first_row = first_row

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self

    def scalar(self):
        return self._scalar_value

    def first(self):
        return self._first_row


@pytest.fixture
def fake_db():
    """AsyncMock that behaves like an async SQLAlchemy session."""
    session = AsyncMock()
    session.execute.return_value = FakeResult()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    return session


class FakeAnalyticsSession:
    """Context manager that yields a fake analytics DB session."""
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def fake_analytics_db():
    """Fake analytics database session with context manager."""
    db = Mock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def fake_analytics_session(fake_analytics_db):
    """Returns a FakeAnalyticsSession wrapping fake_analytics_db."""
    return FakeAnalyticsSession(fake_analytics_db)
