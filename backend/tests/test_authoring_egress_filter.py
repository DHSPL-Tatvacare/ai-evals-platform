"""Phase 1 Step 9 — egress credential filter on lookup results.

Acceptance: a fixture lookup result containing an `api_key` field is
blocked at build_outcome / lookup wrapper. CREDENTIAL_LEAK_BLOCKED with
empty payload.
"""
from __future__ import annotations

import json
import time
import unittest
import uuid
from types import SimpleNamespace

from app.services.orchestration_authoring.lookup_models import (
    contains_credential_fields,
)
from app.services.orchestration_authoring.orchestration_authoring_pack import (
    _lookup_result_json,
)


class LookupEgressFilterTests(unittest.TestCase):
    def test_clean_payload_passes_through(self) -> None:
        payload = {'items': [{'id': str(uuid.uuid4()), 'name': 'wati-prod'}]}
        result = _lookup_result_json(
            started=time.monotonic(),
            summary='1 connection',
            payload=payload,
            tool_name='list_provider_connections',
        )
        decoded = json.loads(result)
        self.assertEqual(decoded['status'], 'ok')
        self.assertEqual(decoded['payload'], payload)

    def test_payload_with_api_key_is_blocked(self) -> None:
        payload = {
            'items': [
                {'id': 'x', 'name': 'wati-prod', 'api_key': 'sk-abc'},
            ],
        }
        result = _lookup_result_json(
            started=time.monotonic(),
            summary='1 connection',
            payload=payload,
            tool_name='list_provider_connections',
        )
        decoded = json.loads(result)
        self.assertEqual(decoded['status'], 'error')
        self.assertEqual(decoded['meta']['reason_code'], 'CREDENTIAL_LEAK_BLOCKED')

    def test_payload_with_nested_config_encrypted_is_blocked(self) -> None:
        payload = {
            'items': [
                {'id': 'x', 'meta': {'extra': {'config_encrypted': b'\x00' * 8}}},
            ],
        }
        result = _lookup_result_json(
            started=time.monotonic(),
            summary='1 connection',
            payload=payload,
            tool_name='list_provider_connections',
        )
        decoded = json.loads(result)
        self.assertEqual(decoded['meta']['reason_code'], 'CREDENTIAL_LEAK_BLOCKED')

    def test_blocklist_is_case_insensitive(self) -> None:
        payload = {'API_KEY': 'leak'}
        # The walker lowercases keys before checking the blocklist.
        self.assertEqual(contains_credential_fields(payload), 'API_KEY')


class PackBuildOutcomeFilterTests(unittest.TestCase):
    """Decision §R5 binds the egress filter to `CapabilityPack.build_outcome`.

    v3 routes through SpecialistResult JSON and never calls build_outcome,
    but the filter MUST also be wired here so that a future harness path
    that does go through build_outcome cannot regress R5.
    """

    def test_build_outcome_blocks_credential_field(self) -> None:
        from app.services.orchestration_authoring.orchestration_authoring_pack import (
            OrchestrationAuthoringPack,
        )

        pack = OrchestrationAuthoringPack()
        outcome = pack.build_outcome(
            'list_provider_connections',
            {'items': [{'id': 'x', 'api_key': 'leak'}]},
        )
        self.assertEqual(outcome.get('reason_code'), 'CREDENTIAL_LEAK_BLOCKED')

    def test_build_outcome_passes_clean_payload(self) -> None:
        from app.services.orchestration_authoring.orchestration_authoring_pack import (
            OrchestrationAuthoringPack,
        )

        pack = OrchestrationAuthoringPack()
        outcome = pack.build_outcome(
            'list_provider_connections',
            {'items': [{'id': 'x', 'name': 'wati-prod'}]},
        )
        self.assertNotEqual(outcome.get('reason_code'), 'CREDENTIAL_LEAK_BLOCKED')


if __name__ == '__main__':
    unittest.main()
