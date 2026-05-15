"""Phase 3 Step 4 — `build_outcome` egress filter via the canonical
recursive walker.

Decision §R5: any tool result containing a forbidden field MUST be
blocked at build_outcome. The chat receives a generic error envelope;
the audit log records the offending field name + tool name (never in
the user-facing payload).
"""
from __future__ import annotations

import logging
import unittest

from app.services.orchestration_authoring.audit import authoring_logger
from app.services.orchestration_authoring.orchestration_authoring_pack import (
    OrchestrationAuthoringPack,
)


class _Capturing(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class BuildOutcomeFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.handler = _Capturing()
        authoring_logger.addHandler(self.handler)
        self._prev_level = authoring_logger.level
        authoring_logger.setLevel(logging.DEBUG)

    def tearDown(self) -> None:
        authoring_logger.removeHandler(self.handler)
        authoring_logger.setLevel(self._prev_level)

    def test_clean_payload_passes_through(self) -> None:
        pack = OrchestrationAuthoringPack()
        outcome = pack.build_outcome(
            'list_provider_connections',
            {'items': [{'id': 'x', 'name': 'wati-prod'}]},
        )
        self.assertNotEqual(outcome.get('reason_code'), 'CREDENTIAL_LEAK_BLOCKED')

    def test_top_level_credential_blocked(self) -> None:
        pack = OrchestrationAuthoringPack()
        outcome = pack.build_outcome(
            'list_provider_connections',
            {'items': [{'id': 'x', 'api_key': 'sk-leak'}]},
        )
        self.assertEqual(outcome.get('reason_code'), 'CREDENTIAL_LEAK_BLOCKED')

    def test_nested_credential_blocked(self) -> None:
        pack = OrchestrationAuthoringPack()
        outcome = pack.build_outcome(
            'list_provider_connections',
            {'items': [{'id': 'x', 'meta': {'inner': {'config_encrypted': b'\x00'}}}]},
        )
        self.assertEqual(outcome.get('reason_code'), 'CREDENTIAL_LEAK_BLOCKED')

    def test_user_facing_payload_does_not_contain_field_name(self) -> None:
        pack = OrchestrationAuthoringPack()
        outcome = pack.build_outcome(
            'list_provider_connections',
            {'items': [{'id': 'x', 'api_key': 'sk-leak'}]},
        )
        # The summary / payload returned to the chat must NOT contain the
        # offending field name; the security guarantee is that the LLM
        # never sees credential field names so it can't echo them.
        rendered = repr(outcome)
        self.assertNotIn('api_key', rendered)
        self.assertNotIn('sk-leak', rendered)

    def test_blocked_call_emits_audit_line(self) -> None:
        pack = OrchestrationAuthoringPack()
        pack.build_outcome(
            'list_provider_connections',
            {'items': [{'id': 'x', 'api_key': 'sk-leak'}]},
        )
        emitted = [
            r for r in self.handler.records
            if isinstance(r.args, dict) and r.args.get('event') == 'authoring_tool_call'
        ]
        self.assertEqual(len(emitted), 1)
        payload = emitted[0].args
        assert isinstance(payload, dict)
        self.assertEqual(payload['validation_result'], 'credential_leak_blocked')
        self.assertEqual(payload['tool'], 'list_provider_connections')

    def test_blocked_call_logs_field_and_tool_name_in_warning(self) -> None:
        pack = OrchestrationAuthoringPack()
        pack.build_outcome(
            'list_provider_connections',
            {'items': [{'id': 'x', 'meta': {'api_key': 'sk-leak'}}]},
        )
        warnings = [
            r for r in self.handler.records
            if r.levelno == logging.WARNING and 'build_outcome egress filter blocked' in r.getMessage()
        ]
        self.assertEqual(len(warnings), 1)
        message = warnings[0].getMessage()
        # Field name and tool name are in the log line; not in the user
        # payload (asserted in the previous test).
        self.assertIn('api_key', message)
        self.assertIn('list_provider_connections', message)


if __name__ == '__main__':
    unittest.main()
