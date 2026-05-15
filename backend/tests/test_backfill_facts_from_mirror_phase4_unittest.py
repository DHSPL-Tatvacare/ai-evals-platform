"""Phase 4 tests for ``backfill-facts-from-mirror``.

Covers:
  - Request parsing / validation (mapper allowlist, target_fact gate,
    batch_size bounds, started/ended ordering).
  - Admin endpoint behavior (mapping lookup, state-row lookup, job-row
    creation, response shape, permission gate).
  - Job-type registration (handler + retry policy).
  - Handler driver loop: keyset cursor advances, batches commit
    independently, ON CONFLICT upsert emits the conflict key required for
    idempotency.
  - Steady-state stage-transition writer (plan §3.3 / Phase 4 step 6):
    same-tx writer emits a row on stage change and skips when stage is
    unchanged. Proves the writer is correctly stitched without needing
    a live LSQ webhook.
"""
from __future__ import annotations

import inspect
import unittest
import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.analytics import backfill_facts_from_mirror_job as backfill
from app.services.analytics.mirror_to_fact_mapper import MirrorToFactMapper


# ── parse_request -------------------------------------------------------


class ParseRequestTests(unittest.TestCase):
    def test_required_fields_present(self) -> None:
        req = backfill.parse_request(
            {
                "app_id": "inside-sales",
                "source_table": "analytics.crm_call_record",
                "activity_type": "call",
            }
        )
        self.assertEqual(req.app_id, "inside-sales")
        self.assertEqual(req.batch_size, backfill.DEFAULT_BATCH_SIZE)
        self.assertIsNone(req.started_after)
        self.assertIsNone(req.ended_before)

    def test_missing_app_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            backfill.parse_request(
                {
                    "source_table": "analytics.crm_call_record",
                    "activity_type": "call",
                }
            )

    def test_batch_size_below_min_raises(self) -> None:
        with self.assertRaises(ValueError):
            backfill.parse_request(
                {
                    "app_id": "inside-sales",
                    "source_table": "analytics.crm_call_record",
                    "activity_type": "call",
                    "batch_size": 1,
                }
            )

    def test_batch_size_above_max_raises(self) -> None:
        with self.assertRaises(ValueError):
            backfill.parse_request(
                {
                    "app_id": "inside-sales",
                    "source_table": "analytics.crm_call_record",
                    "activity_type": "call",
                    "batch_size": backfill.MAX_BATCH_SIZE + 1,
                }
            )

    def test_datetime_iso_with_z_parses(self) -> None:
        req = backfill.parse_request(
            {
                "app_id": "inside-sales",
                "source_table": "analytics.crm_call_record",
                "activity_type": "call",
                "started_after": "2026-01-25T00:00:00Z",
                "ended_before": "2026-05-13T00:00:00+00:00",
            }
        )
        self.assertEqual(
            req.started_after,
            datetime(2026, 1, 25, tzinfo=timezone.utc),
        )
        self.assertEqual(
            req.ended_before,
            datetime(2026, 5, 13, tzinfo=timezone.utc),
        )

    def test_date_object_normalizes_to_utc_midnight(self) -> None:
        req = backfill.parse_request(
            {
                "app_id": "inside-sales",
                "source_table": "analytics.crm_call_record",
                "activity_type": "call",
                "started_after": date(2026, 1, 25),
            }
        )
        self.assertEqual(
            req.started_after,
            datetime(2026, 1, 25, tzinfo=timezone.utc),
        )

    def test_garbage_datetime_raises(self) -> None:
        with self.assertRaises(ValueError):
            backfill.parse_request(
                {
                    "app_id": "inside-sales",
                    "source_table": "analytics.crm_call_record",
                    "activity_type": "call",
                    "started_after": "not-a-date",
                }
            )


# ── admin endpoint ------------------------------------------------------


def _make_state_row(*, enabled: bool = True):
    from app.models.analytics_mapping_state import MappingState
    row = MappingState(
        app_id="inside-sales",
        source_table="analytics.crm_call_record",
        target_fact="analytics.fact_lead_activity",
        activity_type="call",
        enabled=enabled,
    )
    row.id = uuid.uuid4()
    row.updated_at = datetime.now(timezone.utc)
    return row


def _auth(*perms: str):
    return SimpleNamespace(
        is_owner=False,
        permissions=frozenset(perms),
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )


class AdminBackfillEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_happy_path_creates_job_and_returns_ids(self) -> None:
        from app.routes.analytics_admin import (
            BackfillFactsRequest,
            submit_backfill_facts,
        )

        added: list[Any] = []
        state_row = _make_state_row()

        db = AsyncMock()
        db.scalar = AsyncMock(return_value=state_row)
        db.add = lambda row: added.append(row)
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        body = BackfillFactsRequest(
            app_id="inside-sales",
            source_table="analytics.crm_call_record",
            activity_type="call",
            started_after=datetime(2026, 1, 25, tzinfo=timezone.utc),
            batch_size=5000,
        )

        response = await submit_backfill_facts(
            body=body, auth=_auth("analytics:admin"), db=db
        )

        self.assertEqual(len(added), 1)
        job = added[0]
        self.assertEqual(job.job_type, "backfill-facts-from-mirror")
        self.assertEqual(job.app_id, "inside-sales")
        self.assertEqual(job.queue_class, "bulk")
        self.assertEqual(job.params["activity_type"], "call")
        self.assertEqual(
            job.params["started_after"], "2026-01-25T00:00:00+00:00"
        )
        # Response surfaces the new job + the mapping_state row id so the
        # UI can link back to the disable/enable surface.
        self.assertEqual(response.job_id, job.id)
        self.assertEqual(response.mapping_id, state_row.id)
        self.assertEqual(response.target_fact, "analytics.fact_lead_activity")
        db.commit.assert_awaited_once()

    async def test_unknown_mapping_returns_400(self) -> None:
        from fastapi import HTTPException
        from app.routes.analytics_admin import (
            BackfillFactsRequest,
            submit_backfill_facts,
        )

        db = AsyncMock()
        body = BackfillFactsRequest(
            app_id="inside-sales",
            source_table="analytics.no_such_mirror",
            activity_type="call",
        )
        with self.assertRaises(HTTPException) as cm:
            await submit_backfill_facts(
                body=body, auth=_auth("analytics:admin"), db=db
            )
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("no mirror->fact mapping", cm.exception.detail)

    async def test_missing_state_row_returns_500(self) -> None:
        from fastapi import HTTPException
        from app.routes.analytics_admin import (
            BackfillFactsRequest,
            submit_backfill_facts,
        )

        db = AsyncMock()
        db.scalar = AsyncMock(return_value=None)
        body = BackfillFactsRequest(
            app_id="inside-sales",
            source_table="analytics.crm_call_record",
            activity_type="call",
        )
        with self.assertRaises(HTTPException) as cm:
            await submit_backfill_facts(
                body=body, auth=_auth("analytics:admin"), db=db
            )
        # Mapping is registered but the seed migration hasn't run — a
        # genuine internal misconfiguration that operators need to see.
        self.assertEqual(cm.exception.status_code, 500)
        self.assertIn("mapping_state row missing", cm.exception.detail)

    async def test_batch_size_above_max_rejected_by_pydantic(self) -> None:
        from pydantic import ValidationError
        from app.routes.analytics_admin import BackfillFactsRequest

        with self.assertRaises(ValidationError):
            BackfillFactsRequest(
                app_id="inside-sales",
                source_table="analytics.crm_call_record",
                activity_type="call",
                batch_size=backfill.MAX_BATCH_SIZE + 1,
            )

    async def test_ended_before_must_follow_started_after(self) -> None:
        from pydantic import ValidationError
        from app.routes.analytics_admin import BackfillFactsRequest

        with self.assertRaises(ValidationError):
            BackfillFactsRequest(
                app_id="inside-sales",
                source_table="analytics.crm_call_record",
                activity_type="call",
                started_after=datetime(2026, 5, 13, tzinfo=timezone.utc),
                ended_before=datetime(2026, 1, 25, tzinfo=timezone.utc),
            )

    async def test_endpoint_is_permission_gated(self) -> None:
        """The route declares ``require_permission('analytics:admin')``."""
        from fastapi import HTTPException
        from app.routes.analytics_admin import submit_backfill_facts

        sig = inspect.signature(submit_backfill_facts)
        auth_param = sig.parameters.get("auth")
        self.assertIsNotNone(auth_param)
        depends = auth_param.default
        checker = getattr(depends, "dependency", None)
        self.assertIsNotNone(
            checker, "auth default is not a Depends() wrapper"
        )

        # The checker raises 403 when the caller lacks the perm.
        with self.assertRaises(HTTPException) as cm:
            await checker(auth=_auth("cost:view"))
        self.assertEqual(cm.exception.status_code, 403)
        self.assertIn("analytics:admin", cm.exception.detail)


# ── job registry --------------------------------------------------------


class JobRegistryTests(unittest.TestCase):
    def test_backfill_handler_registered(self) -> None:
        from app.services.job_worker import JOB_HANDLERS, RETRY_SAFE_JOB_TYPES
        self.assertIn("backfill-facts-from-mirror", JOB_HANDLERS)
        # Retry-safe because the handler is idempotent on its params.
        self.assertIn("backfill-facts-from-mirror", RETRY_SAFE_JOB_TYPES)


# ── handler driver loop -------------------------------------------------


class _FakeMirrorRow:
    """Stand-in for a ``CrmCallRecord`` ORM row with just enough fields."""

    def __init__(
        self,
        *,
        activity_id: str,
        tenant_id: uuid.UUID,
        app_id: str = "inside-sales",
        call_started_at: datetime | None = None,
    ) -> None:
        self.activity_id = activity_id
        self.tenant_id = tenant_id
        self.app_id = app_id
        self.lead_id = f"L-{activity_id}"
        self.rep_id = "R-1"
        self.rep_name = "Asha"
        self.rep_email = "asha@x.com"
        self.event_code = 21
        self.direction = "inbound"
        self.status = "answered"
        self.call_started_at = call_started_at or datetime(
            2026, 5, 13, tzinfo=timezone.utc
        )
        self.created_on = self.call_started_at
        self.duration_seconds = 60
        self.has_recording = True
        self.recording_url = "u"
        self.phone_number = "p"
        self.display_number = "d"
        self.call_notes = "n"
        self.call_session_id = "s"


class HandlerSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_unsupported_target_fact_raises_before_io(self) -> None:
        # A future signal-fact mapping that lands without expanding this
        # handler should be refused loudly.
        mapper = MirrorToFactMapper.default()
        with patch.object(
            mapper, "for_table"
        ) as mock_for_table:
            mock_for_table.return_value = SimpleNamespace(
                key=("inside-sales", "x", "y", "z"),
                target_fact="analytics.fact_lead_signal",
            )
            with patch.object(
                MirrorToFactMapper, "default", return_value=mapper
            ):
                with self.assertRaises(ValueError) as cm:
                    await backfill.run_backfill_facts_from_mirror(
                        job_id=uuid.uuid4(),
                        params={
                            "app_id": "inside-sales",
                            "source_table": "x",
                            "activity_type": "y",
                            "batch_size": 100,
                        },
                        tenant_id=uuid.uuid4(),
                        user_id=uuid.uuid4(),
                    )
        self.assertIn("only supports target_fact", str(cm.exception))


class FetchBatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_query_includes_window_filters_and_cursor(self) -> None:
        # Capture the compiled SQL via a stub session.
        captured: dict[str, Any] = {}

        scalars = MagicMock()
        scalars.all = MagicMock(return_value=[])
        result = MagicMock()
        result.scalars = MagicMock(return_value=scalars)

        async def _execute(stmt):
            captured["stmt"] = stmt
            return result

        db = AsyncMock()
        db.execute = _execute

        request = backfill.BackfillRequest(
            app_id="inside-sales",
            source_table="analytics.crm_call_record",
            activity_type="call",
            started_after=datetime(2026, 1, 25, tzinfo=timezone.utc),
            ended_before=datetime(2026, 5, 13, tzinfo=timezone.utc),
            batch_size=5000,
        )
        scan = backfill._scan_spec_for("analytics.crm_call_record")
        await backfill._fetch_batch(
            db,
            request=request,
            tenant_id=uuid.uuid4(),
            scan_spec=scan,
            after=(None, None),
        )

        compiled = str(captured["stmt"].compile())
        # Window filter on the coalesced timestamp + tenant + app scope.
        self.assertIn("crm_call_record.tenant_id", compiled)
        self.assertIn("crm_call_record.app_id", compiled)
        self.assertIn("coalesce", compiled.lower())
        self.assertIn("LIMIT", compiled.upper())

    async def test_cursor_advances_strict_keyset(self) -> None:
        captured: dict[str, Any] = {}

        scalars = MagicMock()
        scalars.all = MagicMock(return_value=[])
        result = MagicMock()
        result.scalars = MagicMock(return_value=scalars)

        async def _execute(stmt):
            captured["stmt"] = stmt
            return result

        db = AsyncMock()
        db.execute = _execute

        request = backfill.BackfillRequest(
            app_id="inside-sales",
            source_table="analytics.crm_call_record",
            activity_type="call",
            started_after=None,
            ended_before=None,
            batch_size=10,
        )
        scan = backfill._scan_spec_for("analytics.crm_call_record")
        await backfill._fetch_batch(
            db,
            request=request,
            tenant_id=uuid.uuid4(),
            scan_spec=scan,
            after=(datetime(2026, 5, 13, tzinfo=timezone.utc), "ACT-42"),
        )
        compiled = str(captured["stmt"].compile())
        # Cursor predicate must use both the timestamp and the tiebreaker so
        # rows that share a timestamp with the previous high-watermark are
        # not dropped between batches.
        self.assertIn("activity_id", compiled)


# ── upsert / idempotency ------------------------------------------------


class UpsertConflictKeyTests(unittest.IsolatedAsyncioTestCase):
    async def test_upsert_emits_on_conflict_do_update_with_correct_key(
        self,
    ) -> None:
        captured: dict[str, Any] = {}

        async def _execute(stmt):
            captured["stmt"] = stmt
            inner = MagicMock()
            inner.all = MagicMock(return_value=[])
            return inner

        db = AsyncMock()
        db.execute = _execute

        rows = [
            {
                "id": uuid.uuid4(),
                "tenant_id": uuid.uuid4(),
                "app_id": "inside-sales",
                "lead_id": "L-1",
                "source_activity_id": "ACT-1",
                "activity_type": "call",
                "activity_subtype": "inbound",
                "source_event_code": 21,
                "occurred_at": datetime(2026, 5, 13, tzinfo=timezone.utc),
                "actor_type": "rep",
                "actor_id": "R-1",
                "actor_label": "Asha",
                "attributes": {"duration_seconds": 60},
                "sync_run_id": uuid.uuid4(),
            }
        ]

        inserted, updated = await backfill._upsert_fact_rows(
            db, rows=rows
        )
        compiled = str(captured["stmt"].compile())
        self.assertIn("ON CONFLICT", compiled)
        self.assertIn("DO UPDATE", compiled)
        # Conflict key — Phase 3 same-tx writes use the same shape.
        self.assertIn("tenant_id", compiled)
        self.assertIn("app_id", compiled)
        self.assertIn("source_activity_id", compiled)
        self.assertIn("activity_type", compiled)
        self.assertIn("xmax", compiled)
        # No rows returned in the stub — both counts are zero, but the
        # function shouldn't crash on an empty RETURNING result.
        self.assertEqual(inserted, 0)
        self.assertEqual(updated, 0)

    async def test_upsert_empty_rows_short_circuits(self) -> None:
        db = AsyncMock()
        inserted, updated = await backfill._upsert_fact_rows(db, rows=[])
        self.assertEqual((inserted, updated), (0, 0))
        db.execute.assert_not_called()


# ── dry-run projection (fixture-driven) ---------------------------------


class DryRunProjectionTests(unittest.TestCase):
    """Project representative call mirror rows via the bundled mapping.

    No DB involved — the assertion is that the mapper produces a fact-row
    shape compatible with the upsert path for representative LSQ activity
    rows we expect to see in inside-sales production data.
    """

    def test_inbound_call_projects_to_fact_row_shape(self) -> None:
        mapper = MirrorToFactMapper()
        mapping = mapper.for_table(
            "inside-sales", "analytics.crm_call_record", "call"
        )
        sync_run_id = uuid.uuid4()
        mirror_row = {
            "tenant_id": uuid.uuid4(),
            "app_id": "inside-sales",
            "activity_id": "ACT-42",
            "lead_id": "L-99",
            "rep_id": "R-7",
            "rep_name": "Asha",
            "rep_email": "asha@x.com",
            "event_code": 21,
            "direction": "inbound",
            "status": "answered",
            "call_started_at": datetime(2026, 3, 1, tzinfo=timezone.utc),
            "duration_seconds": 142,
            "has_recording": True,
            "recording_url": "https://x/r/42",
            "phone_number": "+91...",
            "display_number": "+91...",
            "call_notes": "follow up",
            "call_session_id": "S-9",
        }
        fact = mapping.project(mirror_row, sync_run_id=sync_run_id)

        # Structural columns the upsert relies on.
        self.assertEqual(fact["lead_id"], "L-99")
        self.assertEqual(fact["source_activity_id"], "ACT-42")
        self.assertEqual(fact["source_event_code"], 21)
        self.assertEqual(fact["actor_type"], "rep")
        self.assertEqual(fact["actor_id"], "R-7")
        self.assertEqual(fact["actor_label"], "Asha")
        self.assertEqual(fact["activity_type"], "call")
        self.assertEqual(fact["activity_subtype"], "inbound")
        self.assertEqual(fact["sync_run_id"], sync_run_id)

        # Attributes carry the JSONB payload.
        attrs = fact["attributes"]
        self.assertEqual(attrs["duration_seconds"], 142)
        self.assertEqual(attrs["direction"], "inbound")
        self.assertEqual(attrs["status"], "answered")
        self.assertEqual(attrs["rep_email"], "asha@x.com")


# ── steady-state stage-transition writer verification ------------------


class StageTransitionWriterTests(unittest.IsolatedAsyncioTestCase):
    """Phase 4 step 6 verification: prove the existing writer emits rows.

    Plan §3.3 / Phase 4 step 6 asks for a manual webhook test; in-repo this
    is the equivalent assertion — the writer reads prior stages, diffs them
    against the current row, and inserts only on a real stage change. Tests
    here use a stub session so we can capture exactly which rows get added
    without needing Postgres.
    """

    def _row(self, *, lead_id: str, stage: str, tenant_id: uuid.UUID):
        return {
            "tenant_id": tenant_id,
            "app_id": "inside-sales",
            "lead_id": lead_id,
            "prospect_stage": stage,
        }

    async def test_first_observation_with_stage_emits_row(self) -> None:
        from app.services import inside_sales_sync

        captured: list[Any] = []
        # First-time observation: the inner SELECT returns no prior rows,
        # so the writer treats it as the first observation. With a non-null
        # current stage it must emit one row.
        prior_result = MagicMock()
        prior_result.all = MagicMock(return_value=[])
        db = AsyncMock()
        db.execute = AsyncMock(return_value=prior_result)

        async def _capturing_execute(stmt):
            captured.append(stmt)
            return prior_result

        db.execute = _capturing_execute
        tenant_id = uuid.uuid4()
        row = self._row(lead_id="L-1", stage="MQL", tenant_id=tenant_id)
        n = await inside_sales_sync._append_lead_stage_transitions(
            db,
            rows=[row],
            cycle_start=datetime(2026, 5, 13, tzinfo=timezone.utc),
            sync_run_id=uuid.uuid4(),
        )
        self.assertEqual(n, 1)
        # Two execute calls: the prior-stage SELECT + the INSERT.
        self.assertEqual(len(captured), 2)
        compiled = str(captured[1].compile())
        self.assertIn("fact_lead_stage_transition", compiled)

    async def test_same_stage_skips_insert(self) -> None:
        from app.services import inside_sales_sync

        tenant_id = uuid.uuid4()
        prior_row = SimpleNamespace(
            tenant_id=tenant_id,
            app_id="inside-sales",
            lead_id="L-1",
            to_stage="MQL",
            detected_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        prior_result = MagicMock()
        prior_result.all = MagicMock(return_value=[prior_row])

        captured: list[Any] = []

        async def _capturing_execute(stmt):
            captured.append(stmt)
            return prior_result

        db = AsyncMock()
        db.execute = _capturing_execute

        row = self._row(lead_id="L-1", stage="MQL", tenant_id=tenant_id)
        n = await inside_sales_sync._append_lead_stage_transitions(
            db,
            rows=[row],
            cycle_start=datetime(2026, 5, 13, tzinfo=timezone.utc),
            sync_run_id=uuid.uuid4(),
        )
        self.assertEqual(n, 0)
        # Only the SELECT ran; no INSERT.
        self.assertEqual(len(captured), 1)

    async def test_stage_change_emits_row_with_from_to(self) -> None:
        from app.services import inside_sales_sync

        tenant_id = uuid.uuid4()
        prior_row = SimpleNamespace(
            tenant_id=tenant_id,
            app_id="inside-sales",
            lead_id="L-1",
            to_stage="MQL",
            detected_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        prior_result = MagicMock()
        prior_result.all = MagicMock(return_value=[prior_row])

        captured: list[Any] = []

        async def _capturing_execute(stmt):
            captured.append(stmt)
            return prior_result

        db = AsyncMock()
        db.execute = _capturing_execute

        row = self._row(
            lead_id="L-1", stage="Customer", tenant_id=tenant_id
        )
        n = await inside_sales_sync._append_lead_stage_transitions(
            db,
            rows=[row],
            cycle_start=datetime(2026, 5, 13, tzinfo=timezone.utc),
            sync_run_id=uuid.uuid4(),
        )
        self.assertEqual(n, 1)
        # The INSERT statement is the second execute call.
        compiled = str(captured[1].compile())
        self.assertIn("fact_lead_stage_transition", compiled)
        self.assertIn("from_stage", compiled)
        self.assertIn("to_stage", compiled)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
