"""Explicit supervisor-chain compaction via responses.compact() on the Azure v1 surface.

The supervisor owns the cross-turn previous_response_id chain; once accumulated
context crosses the threshold it's compacted explicitly and the chain continues
from the compacted response id. A CompactionPart marks it for the UI (reusing
the existing part — no new contract).
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services.sherlock_v3.compaction import CONTEXT_COMPACT_THRESHOLD_TOKENS
from app.services.sherlock_v3.runtime import _maybe_compact_supervisor


def _client(compacted_id: str = 'resp_compacted') -> SimpleNamespace:
    compact = AsyncMock(return_value=SimpleNamespace(id=compacted_id))
    return SimpleNamespace(responses=SimpleNamespace(compact=compact))


def _ctx() -> SimpleNamespace:
    return SimpleNamespace(emitter=SimpleNamespace(emit=AsyncMock()))


class SupervisorCompactionTriggerTests(unittest.IsolatedAsyncioTestCase):
    async def test_compacts_and_swaps_chain_head_when_over_threshold(self):
        ctx, client = _ctx(), _client()
        new_id = await _maybe_compact_supervisor(
            ctx=ctx, client=client, model='gpt-5.4',
            last_response_id='resp_original',
            cumulative_tokens=CONTEXT_COMPACT_THRESHOLD_TOKENS,
        )
        client.responses.compact.assert_awaited_once()
        kwargs = client.responses.compact.await_args.kwargs
        self.assertEqual(kwargs['previous_response_id'], 'resp_original')
        self.assertEqual(new_id, 'resp_compacted')  # chain continues from compacted id
        ctx.emitter.emit.assert_awaited_once()
        self.assertEqual(ctx.emitter.emit.await_args.args[0].type, 'compaction')

    async def test_noop_when_under_threshold(self):
        ctx, client = _ctx(), _client()
        new_id = await _maybe_compact_supervisor(
            ctx=ctx, client=client, model='gpt-5.4',
            last_response_id='resp_original',
            cumulative_tokens=CONTEXT_COMPACT_THRESHOLD_TOKENS - 1,
        )
        client.responses.compact.assert_not_awaited()
        ctx.emitter.emit.assert_not_awaited()
        self.assertEqual(new_id, 'resp_original')

    async def test_noop_when_no_chain_head(self):
        ctx, client = _ctx(), _client()
        new_id = await _maybe_compact_supervisor(
            ctx=ctx, client=client, model='gpt-5.4',
            last_response_id=None,
            cumulative_tokens=CONTEXT_COMPACT_THRESHOLD_TOKENS * 10,
        )
        client.responses.compact.assert_not_awaited()
        self.assertIsNone(new_id)


if __name__ == '__main__':
    unittest.main()
