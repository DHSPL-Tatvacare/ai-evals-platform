"""Tests for the ``recover_orphaned_turns`` reconciler.

A Sherlock turn runs as an in-process asyncio task (report_builder route).
A deploy/OOM/SIGKILL — or a cancellation that skipped terminal marking —
strands it in 'queued'/'active'. At boot the owning task is gone, so any
non-terminal turn is orphaned and must be failed so the UI stops waiting.

Uses an in-memory fake session (same approach as the source-sync reconciler
test) because the real model carries columns SQLite can't render.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch


def _make_turn_row(*, status: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        status=status,
        last_error=None,
        last_event_seq=0,
    )


class _FakeResult:
    def __init__(self, rows: list):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    """Feeds the reconciler's single SELECT of non-terminal turns."""

    def __init__(self, *, non_terminal_rows: list):
        self._non_terminal_rows = non_terminal_rows
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _stmt):
        return _FakeResult(self._non_terminal_rows)

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1


class RecoverOrphanedTurnsTests(IsolatedAsyncioTestCase):
    async def _run(self, *, non_terminal_rows: list) -> _FakeSession:
        session = _FakeSession(non_terminal_rows=non_terminal_rows)
        from app.services.report_builder import turn_store

        with patch.object(turn_store, "async_session", lambda: session):
            count = await turn_store.recover_orphaned_turns()
        self.assertEqual(count, len(non_terminal_rows))
        return session

    async def test_active_and_queued_turns_marked_interrupted(self):
        active = _make_turn_row(status="active")
        queued = _make_turn_row(status="queued")

        session = await self._run(non_terminal_rows=[active, queued])

        self.assertEqual(active.status, "interrupted")
        self.assertEqual(queued.status, "interrupted")
        self.assertIn("restart", (active.last_error or "").lower())
        self.assertEqual(session.commits, 1)

    async def test_no_orphans_skips_commit(self):
        session = await self._run(non_terminal_rows=[])
        self.assertEqual(session.commits, 0)
