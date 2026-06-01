"""The backend's user-message echo id MUST derive from the client turn id
(not the internal DB turn primary key), so the chat widget's optimistic
``user-<turnId>`` bubble reconciles by id instead of duplicating.

Regression guard for the Phase-3 blocker: ``ctx.turn_id`` is the DB row id,
which differs from ``client_turn_id`` — echoing off the wrong one renders the
user's question twice until refresh.
"""
from __future__ import annotations

import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.auth.context import AuthContext
from app.services.sherlock_v3 import runtime as runtime_mod
from app.services.sherlock_v3.runtime import SherlockTurnContext, run_turn


class _CapturingEmitter:
    def __init__(self) -> None:
        self.parts: list = []

    async def emit(self, part):
        self.parts.append(part)
        return part

    async def update(self, part):
        return part


def _make_auth() -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email='test@example.com',
        role_id=uuid.uuid4(),
        is_owner=False,
        permissions=frozenset(),
        app_access=frozenset({'voice-rx'}),
    )


class UserMessageEchoIdTests(unittest.IsolatedAsyncioTestCase):
    async def test_echo_id_derives_from_client_turn_id_not_db_turn_id(self) -> None:
        emitter = _CapturingEmitter()
        client_turn_id = 'client-turn-xyz'
        db_turn_pk = uuid.uuid4()  # the DB primary key — DIFFERENT from the client id
        self.assertNotEqual(str(db_turn_pk), client_turn_id)

        ctx = SherlockTurnContext(
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            app_id='voice-rx',
            chat_session_id=uuid.uuid4(),
            turn_id=db_turn_pk,
            client_turn_id=client_turn_id,
            auth=_make_auth(),
            emitter=emitter,  # type: ignore[arg-type]
            previous_response_id=None,
        )

        async def _fake_stream(*_a, **_k):
            return {'input_tokens': 0, 'output_tokens': 0}, None

        with patch.object(runtime_mod, 'get_sherlock_azure_client', new=AsyncMock(return_value=(MagicMock(), 'gpt-4o'))), \
             patch.object(runtime_mod, 'build_supervisor', return_value=object()), \
             patch.object(runtime_mod, '_stream_once', side_effect=_fake_stream):
            await run_turn('How many calls today?', ctx)

        user_parts = [p for p in emitter.parts if p.__class__.__name__ == 'UserMessagePart']
        self.assertEqual(len(user_parts), 1)
        # Matches the client's optimistic `user-${turnId}` so it reconciles.
        self.assertEqual(user_parts[0].id, f'user-{client_turn_id}')
        # And is NOT the DB primary key, which would never match the client.
        self.assertNotEqual(user_parts[0].id, f'user-{db_turn_pk}')


if __name__ == '__main__':
    unittest.main()
