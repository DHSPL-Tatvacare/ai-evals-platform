"""Phase 1 Step 1 — orchestration.authoring pack registers at boot.

The boot validator (`validate_all_app_pack_ids`) iterates registered
packs via `CAPABILITY_PACK_REGISTRY`. This test asserts our pack lands
in the registry after `ensure_packs_registered` runs the *_pack.py
discovery glob.
"""
from __future__ import annotations

import unittest

from app.services.chat_engine.capability_pack import (
    CAPABILITY_PACK_REGISTRY,
    ensure_packs_registered,
    resolve_pack_ids_for_app,
)
from app.services.orchestration_authoring.canvas_patch import (
    CANVAS_PATCH_CONTRACT_ID,
    CanvasPatch,
    CanvasPatchOp,
)
from app.services.orchestration_authoring.orchestration_authoring_pack import (
    PACK_ID,
    REASON_CODES,
)


class AuthoringPackSkeletonTests(unittest.TestCase):
    def test_pack_registers_under_canonical_id(self) -> None:
        ensure_packs_registered()
        self.assertIn(PACK_ID, CAPABILITY_PACK_REGISTRY)
        self.assertEqual(CAPABILITY_PACK_REGISTRY[PACK_ID].pack_id, PACK_ID)

    def test_resolve_pack_ids_accepts_orchestration_authoring(self) -> None:
        ensure_packs_registered()
        ids = resolve_pack_ids_for_app([PACK_ID], app_id='inside-sales')
        self.assertEqual(ids, [PACK_ID])

    def test_artifact_contract_is_canvas_patch(self) -> None:
        pack = CAPABILITY_PACK_REGISTRY[PACK_ID]
        self.assertIn(CANVAS_PATCH_CONTRACT_ID, pack.artifact_contracts)
        self.assertIs(
            pack.artifact_contracts[CANVAS_PATCH_CONTRACT_ID],
            CanvasPatch,
        )

    def test_reason_codes_complete(self) -> None:
        # All 13 codes from the implementation plan §Reason codes.
        expected = {
            'NO_BUILDER_CONTEXT', 'PERMISSION_DENIED', 'APP_FORBIDDEN',
            'WORKFLOW_NOT_FOUND', 'UNKNOWN_NODE_TYPE', 'NODE_CONFIG_INVALID',
            'PREDICATE_INVALID', 'GRAPH_INVALID', 'UUID_NOT_AUTHORIZED',
            'BASE_HASH_MISMATCH', 'CREDENTIAL_LEAK_BLOCKED',
            'PATCH_OPS_EMPTY', 'PATCH_TOO_LARGE',
        }
        self.assertEqual(set(REASON_CODES), expected)

    def test_canvas_patch_round_trip(self) -> None:
        op = CanvasPatchOp(op='add_node', node_id='n1', payload={'node_type': 'sink.complete'})
        patch = CanvasPatch(
            workflow_id='1f2e3d4c-0000-0000-0000-000000000001',
            base_data_hash='abc',
            ops=[op],
            rationale='add a terminal node',
        )
        self.assertEqual(len(patch.ops), 1)
        self.assertEqual(patch.ops[0].op, 'add_node')


if __name__ == '__main__':
    unittest.main()
