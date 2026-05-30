import unittest
from unittest import mock

from sqlalchemy import update

from app.models.sherlock_runtime import SherlockAgentSession
from app.services.report_builder.runtime_store import SherlockAgentSessionState
from app.services.sherlock_v3 import turn_orchestrator


class _Result:
    def __init__(self, value: int) -> None:
        self._value = value

    def first(self):
        return (self._value,)


class _FakeOccupancySession:
    """Emulates the SET-vs-cumulative semantics of the bump UPDATE.

    Inspects the statement's ``.values()`` clause: a literal int means SET
    (last occupancy), a column-bearing SQL expression means a running sum.
    """

    def __init__(self, store: dict[str, int]) -> None:
        self._store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, stmt):
        col = SherlockAgentSession.cumulative_input_tokens
        clause = stmt._values[col.__clause_element__()]
        prior = self._store.get('value', 0)
        if hasattr(clause, 'value') and isinstance(clause.value, int):
            new_value = clause.value
        else:
            # column + increment expression → cumulative sum
            increment = clause.right.value
            new_value = prior + increment
        self._store['value'] = new_value
        return _Result(new_value)

    async def commit(self):
        return None


def _state() -> SherlockAgentSessionState:
    return SherlockAgentSessionState(
        chat_session_id='00000000-0000-0000-0000-000000000001',
        app_id='kaira-bot',
        tenant_id='00000000-0000-0000-0000-000000000002',
        user_id='00000000-0000-0000-0000-000000000003',
        provider='openai',
        model='gpt-5.4',
        message_state=[],
        next_event_seq=0,
    )


class OccupancySetNotCumulativeTests(unittest.IsolatedAsyncioTestCase):
    async def test_occupancy_set_not_cumulative(self):
        store: dict[str, int] = {}
        state = _state()
        estimates = [12_000, 13_000, 12_500]
        observed: list[int] = []
        with mock.patch.object(
            turn_orchestrator, 'async_session',
            lambda: _FakeOccupancySession(store),
        ):
            for est in estimates:
                payload = await turn_orchestrator._bump_and_read_context_window(
                    runtime_session=state,
                    usage={'input_tokens': est},
                )
                observed.append(payload['tokensUsed'])
        # SET semantics: ring equals the current estimate each turn, never the sum.
        self.assertEqual(observed, estimates)
        self.assertNotEqual(observed[-1], sum(estimates))


if __name__ == '__main__':
    unittest.main()
