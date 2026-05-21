"""run_chat_turn must mark the turn terminal even when cancelled.

A Sherlock turn runs as an in-process asyncio task; an SSE client disconnect
or server shutdown cancels it. asyncio.CancelledError is a BaseException, so
the orchestrator's ``except Exception`` does not catch it — without explicit
handling the turn is stranded 'active' forever. This asserts the cancel path
still drives ``mark_turn_terminal(status='interrupted')`` before re-raising.
"""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.report_builder.runtime_store import SherlockAgentSessionState
from app.services.report_builder.turn_store import SherlockConversationTurnState


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self):
        return None

    async def execute(self, _stmt):
        return None


def _session_factory():
    return _FakeSession()


def _runtime_session() -> SherlockAgentSessionState:
    return SherlockAgentSessionState(
        chat_session_id='8d7d7d56-5dca-4f6a-a2c6-4cb5f6f8e221',
        app_id='inside-sales',
        tenant_id='31f8f72f-3bd4-4af0-91af-fc87ed5ebd87',
        user_id='74c1be47-e307-4127-bf0f-a3ef5b2cf38f',
        provider='openai',
        model='gpt-5.4',
        message_state=[],
        next_event_seq=1,
    )


def _turn() -> SherlockConversationTurnState:
    return SherlockConversationTurnState(
        id='2b9c1f3a-1111-2222-3333-444455556666',
        chat_session_id='8d7d7d56-5dca-4f6a-a2c6-4cb5f6f8e221',
        app_id='inside-sales',
        client_turn_id='turn_123',
        provider='openai',
        model='gpt-5.4',
        user_message='summarize results',
        status='queued',
        assistant_message_id=None,
        last_event_seq=0,
    )


class TurnOrchestratorCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_turn_is_marked_interrupted_then_reraised(self):
        from app.services.sherlock_v3 import turn_orchestrator as orch

        mark_terminal = AsyncMock()
        with patch.object(orch, 'async_session', _session_factory), \
             patch.object(orch, 'create_assistant_message', AsyncMock(return_value='msg-1')), \
             patch.object(orch, 'mark_turn_active', AsyncMock()), \
             patch.object(orch, 'PartEmitter', MagicMock()), \
             patch.object(orch, 'run_turn', AsyncMock(side_effect=asyncio.CancelledError())), \
             patch.object(orch, '_price_usage', AsyncMock(return_value={})), \
             patch.object(orch, '_record_turn_llm_usage', AsyncMock()), \
             patch.object(orch, '_bump_and_read_context_window', AsyncMock(return_value={})), \
             patch.object(orch, 'finalize_assistant_message', AsyncMock()), \
             patch.object(orch, 'mark_turn_terminal', mark_terminal):
            with self.assertRaises(asyncio.CancelledError):
                await orch.run_chat_turn(
                    runtime_session=_runtime_session(),
                    user_message='summarize results',
                    turn=_turn(),
                    on_event=AsyncMock(),
                    auth=MagicMock(),
                )

        mark_terminal.assert_awaited_once()
        self.assertEqual(mark_terminal.await_args.kwargs['status'], 'interrupted')


if __name__ == '__main__':
    unittest.main()
