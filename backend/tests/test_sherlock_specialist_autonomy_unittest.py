"""S1-8 — Multi-turn specialist autonomy (the user's core ask).

The data specialist loops with its `submit_sql` tool across BOUNDED internal
turns instead of stopping on the first tool. The two retry mechanisms
(supervisor re-dispatch + in-handler attempt cap) collapse into ONE bounded
cap: `MAX_SPECIALIST_ATTEMPTS`, threaded as `max_turns` on the data
specialist's `as_specialist_tool` wrapper. The supervisor no longer
re-dispatches the specialist for a retry; the specialist owns its retries.
The FE RetryPart feedback now rides off the in-handler attempt number.
"""
from __future__ import annotations

import unittest
import uuid
from unittest.mock import MagicMock, patch

from app.services.sherlock_v3.contracts import RetryPart
from app.services.sherlock_v3.data_specialist import build_data_specialist
from app.services.sherlock_v3.limits import MAX_SPECIALIST_ATTEMPTS


class RunItemStreamEvent:
    """Minimal stand-in whose class name matches the SDK dispatch branch.

    The runtime dispatches on ``type(event).__name__``, so this class name
    must be EXACTLY ``RunItemStreamEvent`` for the tool_called branch to run.
    """

    def __init__(self, *, name: str, item):
        self.name = name
        self.item = item


class _FakeEmitter:
    def __init__(self):
        self.emitted = []

    async def emit(self, part):
        self.emitted.append(part)
        return part

    async def update(self, part):
        self.emitted.append(part)
        return part


def _tool_called_event(*, name: str, call_id: str):
    item = MagicMock()
    item.raw_item = {'name': name, 'call_id': call_id, 'arguments': '{}'}
    return RunItemStreamEvent(name='tool_called', item=item)


class DataSpecialistAutonomyTest(unittest.TestCase):
    def test_data_specialist_uses_bounded_multi_turn(self):
        agent = build_data_specialist(
            MagicMock(), 'kaira-bot', model='gpt-5.4-mini',
        )
        self.assertNotEqual(agent.tool_use_behavior, 'stop_on_first_tool')

    def test_single_retry_cap(self):
        """ONE cap: the data tool's max_turns is MAX_SPECIALIST_ATTEMPTS."""
        captured: dict[str, object] = {}
        from app.services.sherlock_v3 import supervisor as sup_mod

        real_as_tool = sup_mod.as_specialist_tool

        def _spy(agent, *, tool_name, **kwargs):
            if tool_name == 'data_specialist':
                captured['max_turns'] = kwargs.get('max_turns')
            return real_as_tool(agent, tool_name=tool_name, **kwargs)

        with patch.object(sup_mod, 'as_specialist_tool', _spy):
            sup_mod.build_supervisor(
                'kaira-bot',
                MagicMock(),
                supervisor_model='gpt-5.4',
                specialist_model='gpt-5.4-mini',
            )
        self.assertIn('max_turns', captured)
        self.assertEqual(captured['max_turns'], MAX_SPECIALIST_ATTEMPTS)


class SupervisorNoRedispatchRetryTest(unittest.IsolatedAsyncioTestCase):
    async def test_supervisor_does_not_redispatch_for_retry(self):
        """Two supervisor tool_called events for the same specialist must NOT
        make the runtime emit a RetryPart — retries now live inside the
        specialist, so the runtime's re-dispatch retry branch is gone."""
        from app.services.sherlock_v3 import runtime as rt_mod

        ctx = rt_mod.SherlockTurnContext(
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            app_id='kaira-bot',
            chat_session_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
            client_turn_id=str(uuid.uuid4()),
            auth=MagicMock(),
            emitter=_FakeEmitter(),
        )
        from app.services.sherlock_v3.contracts import Attempt
        from app.services.sherlock_v3.data_specialist import _invalid_arg_verdict
        ctx.scratch['_last_data_specialist_attempt'] = Attempt(
            sql='SELECT 1',
            verdict=_invalid_arg_verdict(),
            status='execution_error',
            error_message='boom',
        )

        ev1 = _tool_called_event(name='data_specialist', call_id='call_a')
        ev2 = _tool_called_event(name='data_specialist', call_id='call_b')
        await rt_mod._emit_part_for_sdk_event(ev1, ctx)
        await rt_mod._emit_part_for_sdk_event(ev2, ctx)

        retry_parts = [
            p for p in ctx.emitter.emitted if isinstance(p, RetryPart)
        ]
        self.assertEqual(retry_parts, [])


if __name__ == '__main__':
    unittest.main()
