"""save_draft validates the draft and upserts it in place (no version row).

These cases mock the AsyncSession so the validation path can run without
a live Postgres. The DB-integration suite covers the persistence side via
test_orchestration_routes_unittest (port 5432 required).
"""
from __future__ import annotations

import asyncio
import uuid
import unittest
from unittest.mock import AsyncMock, MagicMock

import app.services.orchestration.nodes  # noqa: F401  (register handlers)
from app.services.orchestration.api.versions import (
    DraftValidationError,
    save_draft,
)


def _make_db(workflow_type: str = "crm") -> tuple[MagicMock, MagicMock]:
    """Mock AsyncSession that returns one Workflow on the only select.

    Returns (db, workflow) so assertions can inspect the upserted draft.
    """
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    workflow = MagicMock()
    workflow.workflow_type = workflow_type
    workflow.app_id = "inside-sales"
    workflow.draft_definition = None
    workflow.draft_updated_at = None

    wf_scalar = MagicMock()
    wf_scalar.scalar_one_or_none = MagicMock(return_value=workflow)

    db.execute = AsyncMock(side_effect=[wf_scalar])
    return db, workflow


class SaveDraftValidationTests(unittest.TestCase):
    def test_partial_draft_with_empty_configs_upserts_no_version_row(self) -> None:
        async def run() -> None:
            db, workflow = _make_db()
            definition = {
                "nodes": [
                    {"id": "src", "type": "source.event_trigger", "config": {}},
                ],
                "edges": [],
            }
            row = await save_draft(
                db, tenant_id=uuid.uuid4(), workflow_id=uuid.uuid4(),
                definition=definition,
            )
            self.assertIs(row, workflow)
            # Draft is written to the workflow row; no WorkflowVersion is added.
            db.add.assert_not_called()
            db.commit.assert_awaited_once()
            self.assertIsNotNone(workflow.draft_definition)
            self.assertIsNotNone(workflow.draft_updated_at)

        asyncio.run(run())

    def test_fabricated_key_rejects_with_structured_errors(self) -> None:
        async def run() -> None:
            db, workflow = _make_db()
            bad = {
                "nodes": [{
                    "id": "src",
                    "type": "source.event_trigger",
                    "config": {"fabricated_key": 1},
                }],
                "edges": [],
            }
            with self.assertRaises(DraftValidationError) as cm:
                await save_draft(
                    db, tenant_id=uuid.uuid4(), workflow_id=uuid.uuid4(),
                    definition=bad,
                )
            self.assertTrue(cm.exception.errors)
            self.assertEqual(cm.exception.errors[0]["node_id"], "src")
            self.assertEqual(cm.exception.errors[0]["field"], "config")
            db.commit.assert_not_awaited()
            self.assertIsNone(workflow.draft_definition)

        asyncio.run(run())

    def test_unknown_node_type_rejects(self) -> None:
        async def run() -> None:
            db, _ = _make_db()
            bad = {
                "nodes": [{"id": "n", "type": "made.up.type", "config": {}}],
                "edges": [],
            }
            with self.assertRaises(DraftValidationError):
                await save_draft(
                    db, tenant_id=uuid.uuid4(), workflow_id=uuid.uuid4(),
                    definition=bad,
                )

        asyncio.run(run())

    def test_missing_workflow_returns_none(self) -> None:
        async def run() -> None:
            db = MagicMock()
            db.add = MagicMock()
            db.commit = AsyncMock()
            wf_scalar = MagicMock()
            wf_scalar.scalar_one_or_none = MagicMock(return_value=None)
            db.execute = AsyncMock(side_effect=[wf_scalar])
            row = await save_draft(
                db, tenant_id=uuid.uuid4(), workflow_id=uuid.uuid4(),
                definition={"nodes": [], "edges": []},
            )
            self.assertIsNone(row)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
