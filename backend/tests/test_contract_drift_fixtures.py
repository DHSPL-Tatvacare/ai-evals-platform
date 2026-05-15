"""Drift-lock parity — backend half.

Reads the JSON fixtures under ``backend/tests/fixtures/contract_drift/`` and
runs them through the canonical ``validate_definition(mode='draft')``. The
frontend mirror (``src/features/orchestration/contracts/__tests__/
contractDriftFixtures.test.ts``) runs the SAME files through ``parseNodeConfig
(mode: 'draft')``. Together they ensure the four historically-drifted node
contracts (``logic.split`` / ``logic.wait`` / ``source.cohort_query`` /
``crm.send_wati``) stay aligned until Phase 16 codegen replaces the mirror.

A change that lands on only one side will fail the matching test on the
other side, surfacing drift in CI rather than at publish-time 422.
"""
from __future__ import annotations

import json
import os
import unittest
from typing import Any

import app.services.orchestration.nodes  # noqa: F401  (register handlers)
from app.services.orchestration.definition_validator import (
    DefinitionValidationError,
    validate_definition,
)


_FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "contract_drift")


def _wf_with(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "nodes": [
            {
                "id": "n",
                "type": node["node_type"],
                "position": {"x": 0, "y": 0},
                "data": {},
                "config": node.get("config") or {},
            }
        ],
        "edges": [],
        "canvas": {},
    }


def _load(name: str) -> dict[str, Any]:
    with open(os.path.join(_FIXTURES_DIR, name)) as fh:
        return json.load(fh)


_VALID_FIXTURES = (
    "logic_split.valid_draft.json",
    "logic_wait.valid_draft.json",
    "source_cohort_query.valid_draft.json",
    "crm_send_wati.valid_draft.json",
)

_INVALID_FIXTURES = (
    "logic_split.invalid_fabricated_key.json",
    "logic_wait.invalid_fabricated_key.json",
    "source_cohort_query.invalid_fabricated_key.json",
    "crm_send_wati.invalid_fabricated_key.json",
)


class ContractDriftFixturesTests(unittest.TestCase):
    """The fixture set must accept the same configs the frontend Zod
    accepts, and reject the same configs the frontend Zod rejects."""

    def test_valid_fixtures_pass_draft_validation(self) -> None:
        for name in _VALID_FIXTURES:
            with self.subTest(fixture=name):
                fixture = _load(name)
                # workflow_type='crm' is fine for every node here — all
                # four are registered with workflow_type='*' or 'crm'.
                validate_definition(
                    _wf_with(fixture), workflow_type="crm", mode="draft",
                )

    def test_invalid_fixtures_reject_with_extra_forbidden(self) -> None:
        for name in _INVALID_FIXTURES:
            with self.subTest(fixture=name):
                fixture = _load(name)
                with self.assertRaises(DefinitionValidationError) as cm:
                    validate_definition(
                        _wf_with(fixture), workflow_type="crm", mode="draft",
                    )
                # Every fixture's offending key surfaces as a config-shaped
                # validation error, not a graph one — locks the diagnostic.
                messages = [e.get("message") or "" for e in cm.exception.errors]
                self.assertTrue(
                    any(
                        "Extra inputs are not permitted" in m
                        or "unsupported filter op" in m
                        for m in messages
                    ),
                    msg=f"{name}: expected an extra-key or unsupported-op rejection, got {messages}",
                )


if __name__ == "__main__":
    unittest.main()
