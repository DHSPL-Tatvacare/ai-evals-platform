"""P9 — an empty-result attempt emits NO ChartPart; a non-empty one emits exactly one."""
from __future__ import annotations

import asyncio
import unittest

from app.services.sherlock_v3.contracts.artifact import Artifact
from app.services.sherlock_v3.contracts.parts import ChartPart
from app.services.sherlock_v3.data_specialist import _emit_chart_parts


class _CollectingEmitter:
    def __init__(self) -> None:
        self.parts: list[object] = []

    async def emit(self, part: object) -> None:
        self.parts.append(part)


def _empty_artifact() -> Artifact:
    return Artifact.model_validate({'kind': 'empty', 'payload': {'kind': 'empty'}})


def _table_artifact() -> Artifact:
    return Artifact.model_validate({
        'kind': 'table',
        'payload': {
            'kind': 'table',
            'columns': [{'name': 'agent', 'label': 'Agent', 'role': 'dimension'}],
            'data': [{'agent': 'a'}],
        },
    })


class EmptyChartGuardTests(unittest.TestCase):
    def test_empty_artifact_emits_no_chart_part(self) -> None:
        emitter = _CollectingEmitter()
        asyncio.run(_emit_chart_parts(emitter=emitter, artifacts=[_empty_artifact()]))
        chart_parts = [p for p in emitter.parts if isinstance(p, ChartPart)]
        self.assertEqual(chart_parts, [])

    def test_non_empty_artifact_emits_exactly_one_chart_part(self) -> None:
        emitter = _CollectingEmitter()
        asyncio.run(_emit_chart_parts(emitter=emitter, artifacts=[_table_artifact()]))
        chart_parts = [p for p in emitter.parts if isinstance(p, ChartPart)]
        self.assertEqual(len(chart_parts), 1)
        self.assertEqual(chart_parts[0].artifact.kind, 'table')

    def test_none_emitter_is_a_noop(self) -> None:
        asyncio.run(_emit_chart_parts(emitter=None, artifacts=[_table_artifact()]))


if __name__ == '__main__':
    unittest.main()
