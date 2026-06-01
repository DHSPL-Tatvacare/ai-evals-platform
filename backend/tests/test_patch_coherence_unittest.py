"""Patch-time coherence: every payload-bound dispatch field must be carried
by the direct upstream source.cohort. Pure function, no DB."""
import unittest

from app.services.orchestration_authoring.patch_coherence import (
    check_bound_fields_carried,
)


def _candidate(*, cohort_payload_fields, send_mappings):
    return {
        "nodes": [
            {
                "id": "src",
                "type": "source.cohort",
                "config": {"mode": "inline", "payload_fields": cohort_payload_fields},
            },
            {
                "id": "send",
                "type": "messaging.send_whatsapp_template",
                "config": {"variable_mappings": send_mappings},
            },
        ],
        "edges": [
            {"id": "e1", "source": "src", "target": "send", "output_id": "default"},
        ],
    }


class CheckBoundFieldsCarriedTest(unittest.TestCase):
    def test_uncarried_payload_field_yields_one_violation(self):
        candidate = _candidate(
            cohort_payload_fields=["name"],
            send_mappings=[
                {"agent_variable": "phone", "source_kind": "payload", "payload_field": "phone"},
            ],
        )
        violations = check_bound_fields_carried(candidate)
        self.assertEqual(len(violations), 1)
        self.assertIn("phone", violations[0])
        self.assertIn("send", violations[0])

    def test_carried_payload_field_yields_no_violation(self):
        candidate = _candidate(
            cohort_payload_fields=["name", "phone"],
            send_mappings=[
                {"agent_variable": "phone", "source_kind": "payload", "payload_field": "phone"},
            ],
        )
        self.assertEqual(check_bound_fields_carried(candidate), [])

    def test_static_kind_mappings_are_ignored(self):
        candidate = _candidate(
            cohort_payload_fields=["name"],
            send_mappings=[
                {"agent_variable": "greeting", "source_kind": "static", "static_value": "hi"},
            ],
        )
        self.assertEqual(check_bound_fields_carried(candidate), [])

    def test_saved_mode_cohort_is_not_flagged(self):
        # Saved cohorts carry payload_fields in the DB, not on the node config;
        # a DB-free check must scope them out instead of flagging a false miss.
        candidate = {
            "nodes": [
                {
                    "id": "src",
                    "type": "source.cohort",
                    "config": {
                        "mode": "saved",
                        "cohort_definition_version_id": "11111111-1111-1111-1111-111111111111",
                        "payload_fields": [],
                    },
                },
                {
                    "id": "send",
                    "type": "messaging.send_whatsapp_template",
                    "config": {
                        "variable_mappings": [
                            {"agent_variable": "phone", "source_kind": "payload", "payload_field": "phone"},
                        ]
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "src", "target": "send", "output_id": "default"},
            ],
        }
        self.assertEqual(check_bound_fields_carried(candidate), [])

    def test_multi_hop_carried_field_is_recognized(self):
        # cohort -> logic.wait -> send: the carrier sits two hops upstream.
        candidate = {
            "nodes": [
                {
                    "id": "src",
                    "type": "source.cohort",
                    "config": {"mode": "inline", "payload_fields": ["phone"]},
                },
                {"id": "wait", "type": "logic.wait", "config": {}},
                {
                    "id": "send",
                    "type": "messaging.send_whatsapp_template",
                    "config": {
                        "variable_mappings": [
                            {"agent_variable": "phone", "source_kind": "payload", "payload_field": "phone"},
                        ]
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "src", "target": "wait", "output_id": "default"},
                {"id": "e2", "source": "wait", "target": "send", "output_id": "default"},
            ],
        }
        self.assertEqual(check_bound_fields_carried(candidate), [])


if __name__ == "__main__":
    unittest.main()
