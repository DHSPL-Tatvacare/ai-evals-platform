import unittest
import uuid

from app.services.sherlock_v3 import runtime
from app.services.sherlock_v3.runtime import SherlockTurnContext


class _StubEmitter:
    async def emit(self, part):
        return part

    async def update(self, part):
        return part


class SomeFutureEvent:
    pass


def _ctx() -> SherlockTurnContext:
    return SherlockTurnContext(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        app_id='kaira-bot',
        chat_session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        client_turn_id=str(uuid.uuid4()),
        auth=object(),  # type: ignore[arg-type]
        emitter=_StubEmitter(),  # type: ignore[arg-type]
    )


class UnknownEventDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_event_is_logged_not_dropped(self):
        with self.assertLogs(runtime.logger, level='DEBUG') as captured:
            await runtime._emit_part_for_sdk_event(SomeFutureEvent(), _ctx())
        joined = '\n'.join(captured.output)
        self.assertIn('unhandled SDK stream event', joined)
        self.assertIn('SomeFutureEvent', joined)


if __name__ == '__main__':
    unittest.main()
