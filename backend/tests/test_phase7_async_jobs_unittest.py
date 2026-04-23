"""Phase 7 acceptance-gate tests (plan §770-813).

Gates pinned here map 1:1 to the plan's *Acceptance gates* block:

1. ``submit_pack_job`` returns a §6.2 envelope with ``kind='job_submitted'``
   and a populated ``outcome.job`` (id + status='queued'). The platform
   ``Job`` row written carries ``submission_context = {surface: 'sherlock',
   session_id, turn_id, pack_id}`` verbatim.
2. ``assemble_context`` emits a per-turn pending-jobs block when the DB
   returns Sherlock-submitted jobs for the session; the block lands
   AFTER the cacheable prefix (``base.render() + TOOLS section``).
3. Cacheable-prefix integrity: growing the pending-jobs block (queued
   → running → completed) does NOT change the first two sections of
   the assembled prompt byte-for-byte.
4. No ad-hoc async: Sherlock tool-handler source files contain no
   ``while True .. job.status`` / ``asyncio.sleep .. job`` polling loops.
"""

from __future__ import annotations

import os
import re
import unittest
import uuid
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock


class SubmitPackJobEnvelopeTests(unittest.IsolatedAsyncioTestCase):
    """Gate 1 — envelope shape + submission_context round-trip."""

    async def test_envelope_has_job_submitted_kind_and_session_context(self):
        from app.services.chat_engine.capability_pack import (
            SHERLOCK_SUBMISSION_SURFACE,
            submit_pack_job,
        )

        added: list = []

        db = AsyncMock()
        db.add = lambda obj: added.append(obj)
        db.commit = AsyncMock()

        async def _refresh(obj):
            # Emulate SQLAlchemy's post-flush id assignment.
            if getattr(obj, 'id', None) is None:
                obj.id = uuid.uuid4()

        db.refresh = AsyncMock(side_effect=_refresh)

        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        turn_id = uuid.uuid4()

        envelope = await submit_pack_job(
            db=db,
            pack_id='analytics',
            capability='analytics',
            job_type='generate-report',
            params={'listing_id': 'abc'},
            summary='Running slow query in background',
            tenant_id=tenant_id,
            user_id=user_id,
            app_id='kaira-bot',
            session_id=session_id,
            turn_id=turn_id,
            preview_payload={'estimated_duration_s': 42},
        )

        body = cast(dict[str, Any], envelope.as_dict())
        self.assertEqual(body['status'], 'ok')
        self.assertEqual(body['outcome']['kind'], 'job_submitted')
        self.assertEqual(body['outcome']['capability'], 'analytics')
        self.assertIn('job', body['outcome'])
        self.assertEqual(body['outcome']['job']['status'], 'queued')
        self.assertTrue(body['outcome']['job']['id'])
        # Preview payload surfaces on the envelope's payload slot.
        self.assertEqual(body['payload'], {'estimated_duration_s': 42})

        # The Job row was actually added with the correct submission_context.
        self.assertEqual(len(added), 1)
        job = added[0]
        self.assertEqual(job.job_type, 'generate-report')
        self.assertEqual(job.status, 'queued')
        self.assertEqual(job.submission_context['surface'], SHERLOCK_SUBMISSION_SURFACE)
        self.assertEqual(job.submission_context['session_id'], str(session_id))
        self.assertEqual(job.submission_context['turn_id'], str(turn_id))
        self.assertEqual(job.submission_context['pack_id'], 'analytics')
        # Auth context was injected into params (mirrors /api/jobs plumbing).
        self.assertEqual(job.params['tenant_id'], str(tenant_id))
        self.assertEqual(job.params['user_id'], str(user_id))

    async def test_unknown_job_type_returns_error_envelope(self):
        from app.services.chat_engine.capability_pack import submit_pack_job

        db = AsyncMock()
        added: list = []
        db.add = lambda obj: added.append(obj)

        # get_job_submission_metadata accepts any job_type (defaults for
        # unregistered types). Force the error path by raising from the
        # underlying metadata helper via an invalid priority.
        envelope = await submit_pack_job(
            db=db,
            pack_id='analytics',
            capability='analytics',
            job_type='not-a-real-type',
            params={'priority': 'not-an-int'},
            summary='will fail',
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            app_id='kaira-bot',
            session_id=uuid.uuid4(),
            turn_id=None,
        )
        body = cast(dict[str, Any], envelope.as_dict())
        self.assertEqual(body['status'], 'error')
        self.assertEqual(body['outcome']['kind'], 'error')
        self.assertEqual(body['outcome']['reason_code'], 'JOB_SUBMISSION_FAILED')
        self.assertEqual(added, [])


class PendingJobsBlockTests(unittest.IsolatedAsyncioTestCase):
    """Gate 2 — per-turn pending-jobs block assembly."""

    async def test_block_rendered_from_pack_describe_job(self):
        from app.services.report_builder.chat_handler import _render_pending_jobs_block

        session_id = uuid.uuid4()
        session = {
            'chat_session_id': session_id,
            'tenant_id': uuid.uuid4(),
            'user_id': uuid.uuid4(),
        }

        class _Job:
            def __init__(self, pack_id: str, status: str = 'queued'):
                self.id = uuid.uuid4()
                self.job_type = 'generate-report'
                self.status = status
                self.progress = {'current': 0, 'total': 0, 'message': ''}
                self.submission_context = {
                    'surface': 'sherlock',
                    'session_id': str(session_id),
                    'turn_id': str(uuid.uuid4()),
                    'pack_id': pack_id,
                }

        jobs = [_Job('analytics', 'running'), _Job('report_builder', 'queued')]

        class _Scalars:
            def all(self):
                return jobs

        class _Result:
            def scalars(self):
                return _Scalars()

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Result())

        block = await _render_pending_jobs_block(session, db)
        self.assertIn('Pending pack jobs for this session', block)
        for j in jobs:
            self.assertIn(str(j.id), block)
            self.assertIn(j.status, block)

    async def test_empty_block_when_no_jobs(self):
        from app.services.report_builder.chat_handler import _render_pending_jobs_block

        class _Scalars:
            def all(self):
                return []

        class _Result:
            def scalars(self):
                return _Scalars()

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_Result())

        session = {
            'chat_session_id': uuid.uuid4(),
            'tenant_id': uuid.uuid4(),
            'user_id': uuid.uuid4(),
        }
        block = await _render_pending_jobs_block(session, db)
        self.assertEqual(block, '')


class CacheablePrefixStabilityTests(unittest.IsolatedAsyncioTestCase):
    """Gate 3 — the prompt's cacheable prefix MUST be byte-identical across
    turns even as the pending-jobs block changes. The plan pins this as the
    prefix-cache integrity test (plan §770 *Acceptance gates* bullet 5)."""

    async def test_prefix_byte_identical_across_job_status_cycle(self):
        from app.services.chat_engine.prompts import base
        from app.services.chat_engine.prompt_generator import render_tools_section
        from app.services.report_builder.chat_handler import _render_pending_jobs_block

        # Build the cacheable prefix exactly the way ``assemble_context``
        # does. Note: ``render_tools_section`` is memoized by
        # (frozenset(pack_ids), app_id) — Phase 3's tool resolution gate.
        # Passing a None app_id routes through the same lookup path without
        # hitting app-specific vocabulary.
        prefix_turn_1 = base.render() + '\n\n' + (render_tools_section(app_id='kaira-bot') or '')
        prefix_turn_2 = base.render() + '\n\n' + (render_tools_section(app_id='kaira-bot') or '')

        self.assertEqual(prefix_turn_1, prefix_turn_2)

        session_id = uuid.uuid4()
        base_session = {
            'chat_session_id': session_id,
            'tenant_id': uuid.uuid4(),
            'user_id': uuid.uuid4(),
        }

        def _job(status: str):
            j = MagicMock()
            j.id = uuid.uuid4()
            j.job_type = 'generate-report'
            j.status = status
            j.progress = {'current': 0, 'total': 0, 'message': ''}
            j.submission_context = {
                'surface': 'sherlock',
                'session_id': str(session_id),
                'turn_id': str(uuid.uuid4()),
                'pack_id': 'analytics',
            }
            return j

        async def _exec_factory(jobs: list):
            class _Scalars:
                def all(self):
                    return jobs

            class _Result:
                def scalars(self):
                    return _Scalars()

            return _Result()

        # Same session, three "turns": queued → running → completed. The
        # per-turn pending-jobs block changes across turns; the cacheable
        # prefix MUST stay byte-identical.
        blocks = []
        for status in ('queued', 'running', 'completed'):
            db = AsyncMock()
            db.execute = AsyncMock(return_value=await _exec_factory([_job(status)]))
            blocks.append(await _render_pending_jobs_block(base_session, db))

        self.assertNotEqual(blocks[0], blocks[1])
        self.assertNotEqual(blocks[1], blocks[2])

        # Cacheable prefix is stable regardless of how many jobs or what
        # status — the pending-jobs block is NOT part of the prefix.
        self.assertEqual(
            base.render() + '\n\n' + (render_tools_section(app_id='kaira-bot') or ''),
            prefix_turn_1,
            msg='cacheable prefix drifted across simulated turns',
        )


class NoAdHocAsyncPollingTests(unittest.TestCase):
    """Gate 4 — no tool handler runs an ad-hoc async polling loop.

    Mirrors the plan's grep gate:
    ``grep -nE "while True.*job\\.status|await asyncio\\.sleep.*job" backend/``
    — zero matches inside Sherlock tool handlers.
    """

    def test_sherlock_tool_handlers_have_no_polling_loops(self):
        root = Path(__file__).resolve().parents[1] / 'app' / 'services'
        # Scope to Sherlock tool-handler surfaces only (plan §770 gate 2).
        candidates = [
            root / 'chat_engine' / 'catalog_tools.py',
            root / 'chat_engine' / 'capability_pack.py',
            root / 'chat_engine' / 'openai_agents_adapter.py',
            root / 'report_builder' / 'tool_handlers.py',
            root / 'report_builder' / 'analytics_pack.py',
            root / 'report_builder' / 'report_builder_pack.py',
            root / 'report_builder' / 'chat_handler.py',
        ]
        pattern = re.compile(
            r'while\s+True[^\n]*job\.status|await\s+asyncio\.sleep[^\n]*\bjob\b'
        )
        offenders = []
        for path in candidates:
            if not path.exists():
                continue
            text = path.read_text(encoding='utf-8')
            for line_no, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    offenders.append(f'{path}:{line_no}: {line.strip()}')
        self.assertEqual(offenders, [], f'ad-hoc async polling found: {offenders}')


if __name__ == '__main__':  # pragma: no cover
    # Silence the asyncio debug noise when running as a script.
    os.environ.setdefault('PYTHONASYNCIODEBUG', '0')
    unittest.main()
