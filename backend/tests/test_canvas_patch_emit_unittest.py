"""Runtime emits exactly one CanvasPatchPart when a specialist returns a canvas_patch artifact."""
import json
import time
import unittest
import uuid

from app.services.orchestration_authoring.canvas_patch import (
    CANVAS_PATCH_CONTRACT_ID,
)
from app.services.sherlock_v3.contracts.parts import (
    CanvasPatchPart,
    SubtaskPart,
    SubtaskStateRunning,
    new_part_id,
)
from app.services.sherlock_v3.contracts.brief import SpecialistBrief, SpecialistScope
from app.services.sherlock_v3.runtime import (
    SherlockTurnContext,
    _close_subtask_on_output,
)


def _canvas_patch_payload() -> dict:
    return {
        'workflow_id': '11111111-1111-1111-1111-111111111111',
        'version_id': None,
        'base_data_hash': 'hash_abc',
        'ops': [
            {
                'op': 'add_node',
                'node_id': 'node_new',
                'payload': {'node_type': 'sink.complete', 'config': {}},
            },
        ],
        'rationale': 'Add a completion sink.',
    }


def _apply_patch_result_json(*, with_artifact: bool = True) -> str:
    artifacts = (
        [{'kind': CANVAS_PATCH_CONTRACT_ID, 'payload': _canvas_patch_payload()}]
        if with_artifact else []
    )
    return json.dumps({
        'kind': 'action',
        'status': 'ok',
        'summary': 'Proposed 1 canvas op(s).',
        'evidence': [],
        'artifacts': artifacts,
        'meta': {'confidence': 0.8, 'latency_ms': 5, 'source_pack_id': 'orchestration.authoring'},
    })


class _FakeEmitter:
    def __init__(self) -> None:
        self.emitted: list = []
        self.updated: list = []

    async def emit(self, part):
        materialized = part.model_copy(update={
            'id': part.id or new_part_id(),
            'chat_session_id': 'sess',
            'seq': len(self.emitted),
            'created_at': int(time.time() * 1000),
        })
        self.emitted.append(materialized)
        return materialized

    async def update(self, part):
        self.updated.append(part)
        return part


class _FakeToolOutputItem:
    def __init__(self, *, call_id: str, output: str) -> None:
        self.raw_item = {'call_id': call_id}
        self.output = output


def _ctx_with_subtask(emitter: _FakeEmitter, *, call_id: str, specialist: str) -> SherlockTurnContext:
    ctx = SherlockTurnContext(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        app_id='inside-sales',
        chat_session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        auth=None,  # type: ignore[arg-type]
        emitter=emitter,  # type: ignore[arg-type]
    )
    subtask = SubtaskPart(
        id=new_part_id(),
        chat_session_id='',
        seq=0,
        created_at=0,
        specialist=specialist,
        call_id=call_id,
        brief=SpecialistBrief(
            question='wire it',
            scope=SpecialistScope(
                tenant_id=str(ctx.tenant_id), app_id=ctx.app_id, user_id=str(ctx.user_id),
            ),
        ),
        state=SubtaskStateRunning(started_at=0),
    )
    ctx.scratch['_subtask_parts_by_call_id'] = {call_id: subtask}
    return ctx


class CanvasPatchEmitTests(unittest.IsolatedAsyncioTestCase):
    async def test_canvas_patch_artifact_emits_exactly_one_canvas_patch_part(self):
        emitter = _FakeEmitter()
        ctx = _ctx_with_subtask(emitter, call_id='call_1', specialist='authoring_specialist')

        await _close_subtask_on_output(
            _FakeToolOutputItem(call_id='call_1', output=_apply_patch_result_json()),
            ctx,
        )

        patch_parts = [p for p in emitter.emitted if isinstance(p, CanvasPatchPart)]
        self.assertEqual(len(patch_parts), 1)
        patch = patch_parts[0].patch
        self.assertEqual(patch.workflow_id, '11111111-1111-1111-1111-111111111111')
        self.assertEqual(patch.base_data_hash, 'hash_abc')
        self.assertEqual(len(patch.ops), 1)
        self.assertEqual(patch.ops[0].op, 'add_node')
        self.assertEqual(patch.ops[0].node_id, 'node_new')
        self.assertEqual(patch.rationale, 'Add a completion sink.')

    async def test_no_canvas_patch_part_when_no_artifact(self):
        emitter = _FakeEmitter()
        ctx = _ctx_with_subtask(emitter, call_id='call_2', specialist='authoring_specialist')

        await _close_subtask_on_output(
            _FakeToolOutputItem(call_id='call_2', output=_apply_patch_result_json(with_artifact=False)),
            ctx,
        )

        self.assertEqual([p for p in emitter.emitted if isinstance(p, CanvasPatchPart)], [])

    async def test_data_specialist_chart_artifact_does_not_emit_canvas_patch(self):
        emitter = _FakeEmitter()
        ctx = _ctx_with_subtask(emitter, call_id='call_3', specialist='data_specialist')
        chart_result = json.dumps({
            'kind': 'data',
            'status': 'ok',
            'summary': 'one chart',
            'evidence': [],
            'artifacts': [{'kind': 'chart', 'payload': {'kind': 'empty'}}],
            'meta': {'confidence': 0.8, 'latency_ms': 1, 'source_pack_id': 'inside-sales'},
        })
        await _close_subtask_on_output(
            _FakeToolOutputItem(call_id='call_3', output=chart_result), ctx,
        )
        self.assertEqual([p for p in emitter.emitted if isinstance(p, CanvasPatchPart)], [])


if __name__ == '__main__':
    unittest.main()
