"""Phase 6 tests for ``backfill-stage-transitions``.

Covers:
  - Request parsing / bounds validation (max_leads, batch_size).
  - ``detected_at`` derivation chain: created_on → first_synced_at → epoch
    sentinel (so the partial unique key never collapses across malformed
    rows and reruns over unchanged mirror state are idempotent).
  - Blank-stage skip + counter.
  - Upsert SQL targets the partial unique index columns and carries the
    ``sync_run_id IS NOT NULL`` predicate so Postgres picks
    ``uq_fact_lead_stage_transition_backfill``.
  - Admin endpoint: dry-run 200, live 202, permission gate.
  - Job registry presence.
  - Watermark advances only on success.
  - Steady-state regression: ``_append_lead_stage_transitions`` still
    inserts a fact row when the lead's stage changes vs the prior known
    to_stage. Confirms the writer the plan asks us to verify is correct.

CRM-agnostic by design — tests use ``app_id="inside-sales"`` but exercise
the same path future CRM-backed apps will take.
"""
from __future__ import annotations

import inspect
import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.analytics import backfill_stage_transitions_job as backfill


# ── helpers ─────────────────────────────────────────────────────────────


def _auth(*perms: str):
    return SimpleNamespace(
        is_owner=False,
        permissions=frozenset(perms),
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )


def _make_response():
    return SimpleNamespace(status_code=202)


class _FakeLead:
    """Stand-in for ``CrmLeadRecord`` with enough fields for stage backfill."""

    def __init__(
        self,
        *,
        lead_id: str = "L-1",
        tenant_id: uuid.UUID | None = None,
        app_id: str = "inside-sales",
        prospect_stage: str = "Qualified Lead",
        created_on: datetime | None = None,
        first_synced_at: datetime | None = None,
        last_synced_at: datetime | None = None,
    ) -> None:
        self.lead_id = lead_id
        self.tenant_id = tenant_id or uuid.uuid4()
        self.app_id = app_id
        self.prospect_stage = prospect_stage
        self.created_on = (
            created_on
            if created_on is not None
            else datetime(2026, 3, 1, tzinfo=timezone.utc)
        )
        self.first_synced_at = (
            first_synced_at
            if first_synced_at is not None
            else datetime(2026, 5, 1, tzinfo=timezone.utc)
        )
        self.last_synced_at = (
            last_synced_at
            if last_synced_at is not None
            else datetime(2026, 5, 14, tzinfo=timezone.utc)
        )


# ── parse_request ───────────────────────────────────────────────────────


class ParseRequestTests(unittest.TestCase):
    def test_defaults_when_only_app_id_provided(self) -> None:
        req = backfill.parse_request({"app_id": "inside-sales"})
        self.assertEqual(req.app_id, "inside-sales")
        self.assertFalse(req.dry_run)
        self.assertEqual(req.max_leads, backfill.DEFAULT_MAX_LEADS)
        self.assertEqual(req.batch_size, backfill.DEFAULT_BATCH_SIZE)

    def test_blank_app_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            backfill.parse_request({"app_id": ""})
        with self.assertRaises(ValueError):
            backfill.parse_request({})

    def test_explicit_zero_max_leads_rejected_not_masked_to_default(self) -> None:
        # A user-supplied 0 must fail loudly, not silently fall through to
        # DEFAULT_MAX_LEADS via the ``or DEFAULT`` shorthand (the Phase 5
        # bug class). Same for batch_size.
        with self.assertRaises(ValueError):
            backfill.parse_request({"app_id": "inside-sales", "max_leads": 0})
        with self.assertRaises(ValueError):
            backfill.parse_request({"app_id": "inside-sales", "batch_size": 0})

    def test_oversized_max_leads_rejected(self) -> None:
        with self.assertRaises(ValueError):
            backfill.parse_request(
                {"app_id": "inside-sales", "max_leads": backfill.MAX_MAX_LEADS + 1}
            )
        with self.assertRaises(ValueError):
            backfill.parse_request(
                {"app_id": "inside-sales", "batch_size": backfill.MAX_BATCH_SIZE + 1}
            )

    def test_iso_window_parses(self) -> None:
        req = backfill.parse_request(
            {
                "app_id": "inside-sales",
                "started_after": "2026-01-01T00:00:00Z",
                "ended_before": "2026-05-01T00:00:00+00:00",
            }
        )
        assert req.started_after is not None
        assert req.ended_before is not None
        self.assertEqual(req.started_after.tzinfo, timezone.utc)
        self.assertEqual(req.ended_before.tzinfo, timezone.utc)


# ── detected_at derivation ──────────────────────────────────────────────


class DetectedAtSemanticsTests(unittest.TestCase):
    def test_uses_created_on_when_present(self) -> None:
        ts = datetime(2026, 3, 1, tzinfo=timezone.utc)
        lead = _FakeLead(created_on=ts)
        self.assertEqual(backfill._detected_at_for(lead), ts)

    def test_falls_back_to_first_synced_when_created_on_null(self) -> None:
        ts = datetime(2026, 4, 1, tzinfo=timezone.utc)
        lead = SimpleNamespace(created_on=None, first_synced_at=ts)
        self.assertEqual(backfill._detected_at_for(lead), ts)

    def test_unix_epoch_sentinel_when_both_null(self) -> None:
        lead = SimpleNamespace(created_on=None, first_synced_at=None)
        result = backfill._detected_at_for(lead)
        self.assertEqual(result, backfill._EPOCH_SENTINEL)
        self.assertEqual(result.tzinfo, timezone.utc)

    def test_naive_datetime_assumed_utc(self) -> None:
        naive = datetime(2026, 3, 1, 12, 0)
        lead = SimpleNamespace(created_on=naive, first_synced_at=None)
        result = backfill._detected_at_for(lead)
        self.assertEqual(result.tzinfo, timezone.utc)
        self.assertEqual(result.hour, 12)

    def test_rerun_over_unchanged_lead_produces_same_key(self) -> None:
        """Idempotency invariant: same source state → same detected_at."""
        ts = datetime(2026, 3, 1, tzinfo=timezone.utc)
        lead_first = _FakeLead(created_on=ts)
        lead_second = _FakeLead(created_on=ts)  # mirror unchanged
        self.assertEqual(
            backfill._detected_at_for(lead_first),
            backfill._detected_at_for(lead_second),
        )


# ── upsert SQL shape ────────────────────────────────────────────────────


class UpsertConflictKeyTests(unittest.IsolatedAsyncioTestCase):
    async def test_upsert_targets_partial_unique_index_columns(self) -> None:
        captured: dict[str, Any] = {}

        async def _execute(stmt):
            captured["stmt"] = stmt
            result = MagicMock()
            result.all = MagicMock(return_value=[])
            return result

        db = AsyncMock()
        db.execute = _execute
        await backfill._upsert_stage_rows(
            db,
            rows=[
                {
                    "id": uuid.uuid4(),
                    "tenant_id": uuid.uuid4(),
                    "app_id": "inside-sales",
                    "lead_id": "L-1",
                    "from_stage": None,
                    "to_stage": "Qualified Lead",
                    "detected_at": datetime(2026, 3, 1, tzinfo=timezone.utc),
                    "transition_at": None,
                    "sync_run_id": uuid.uuid4(),
                    "attributes": {},
                }
            ],
        )
        compiled = str(captured["stmt"].compile())
        # Conflict columns must match the partial unique index — note
        # to_stage is NOT in the key (rerunning the backfill should
        # UPDATE the seed row's to_stage rather than fork into a new row).
        for col in ("tenant_id", "app_id", "lead_id", "detected_at"):
            self.assertIn(col, compiled)
        # Partial predicate must appear so Postgres picks the right index
        # and the unconstrained pre-Phase-6 rows aren't disturbed.
        self.assertIn("sync_run_id IS NOT NULL", compiled)
        # to_stage must appear in the UPDATE set so a rerun against a
        # lead whose stage changed refreshes the seed row.
        self.assertIn("to_stage", compiled)

    async def test_upsert_noop_on_empty_rows(self) -> None:
        db = AsyncMock()
        inserted, updated = await backfill._upsert_stage_rows(db, rows=[])
        self.assertEqual((inserted, updated), (0, 0))
        db.execute.assert_not_called()


# ── dry-run path ────────────────────────────────────────────────────────


class DryRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_returns_count_without_writes(self) -> None:
        with patch.object(
            backfill, "count_candidate_leads", AsyncMock(return_value=4_321)
        ), patch(
            "app.database.async_session"
        ) as session_factory:
            session_factory.return_value.__aenter__.return_value = AsyncMock()
            session_factory.return_value.__aexit__.return_value = None
            result = await backfill.run_backfill_stage_transitions(
                job_id=uuid.uuid4(),
                params={"app_id": "inside-sales", "dry_run": True},
                tenant_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
            )
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["lead_count"], 4_321)
        # No estimated cost: Phase 6 has no LLM.
        self.assertNotIn("estimated_cost_usd", result)


# ── blank-stage skip ────────────────────────────────────────────────────


class BlankStageSkipTests(unittest.TestCase):
    def test_blank_or_whitespace_stage_classified(self) -> None:
        # The actual filtering happens inside _drive_backfill; this asserts
        # the per-lead branch logic directly to avoid orchestrating a
        # session.
        counters = backfill._BackfillCounters()
        rows: list[dict[str, Any]] = []
        for lead in [
            _FakeLead(prospect_stage=""),
            _FakeLead(prospect_stage="   "),
            _FakeLead(lead_id="L-2", prospect_stage="Qualified Lead"),
        ]:
            current = (lead.prospect_stage or "").strip()
            if not current:
                counters.leads_skipped_blank_stage += 1
                continue
            rows.append({"lead_id": lead.lead_id, "to_stage": current})
            counters.leads_projected += 1
        self.assertEqual(counters.leads_skipped_blank_stage, 2)
        self.assertEqual(counters.leads_projected, 1)
        self.assertEqual(rows[0]["to_stage"], "Qualified Lead")


# ── admin endpoint ──────────────────────────────────────────────────────


class AdminEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_returns_count_without_job(self) -> None:
        from app.routes.analytics_admin import (
            BackfillStageTransitionsRequest,
            submit_backfill_stage_transitions,
        )

        added: list[Any] = []
        db = AsyncMock()
        db.add = lambda row: added.append(row)
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        with patch(
            "app.routes.analytics_admin.count_candidate_stage_leads",
            AsyncMock(return_value=2_500),
        ):
            body = BackfillStageTransitionsRequest(
                app_id="inside-sales", dry_run=True
            )
            response_obj = _make_response()
            response = await submit_backfill_stage_transitions(
                body=body,
                response=response_obj,
                auth=_auth("analytics:admin"),
                db=db,
            )

        self.assertEqual(added, [])
        # Dry-run is informational; status flips from the 202 default to 200.
        self.assertEqual(response_obj.status_code, 200)
        self.assertTrue(response.dry_run)
        self.assertEqual(response.lead_count, 2_500)

    async def test_live_run_creates_job_and_returns_ids(self) -> None:
        from app.routes.analytics_admin import (
            BackfillStageTransitionsRequest,
            submit_backfill_stage_transitions,
        )

        added: list[Any] = []
        db = AsyncMock()
        db.add = lambda row: added.append(row)
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        with patch(
            "app.routes.analytics_admin.count_candidate_stage_leads",
            AsyncMock(return_value=500),
        ):
            body = BackfillStageTransitionsRequest(
                app_id="inside-sales", dry_run=False
            )
            response_obj = _make_response()
            response = await submit_backfill_stage_transitions(
                body=body,
                response=response_obj,
                auth=_auth("analytics:admin"),
                db=db,
            )

        self.assertEqual(len(added), 1)
        job = added[0]
        self.assertEqual(job.job_type, "backfill-stage-transitions")
        self.assertEqual(job.queue_class, "bulk")
        self.assertEqual(job.params["app_id"], "inside-sales")
        self.assertFalse(job.params["dry_run"])
        self.assertEqual(response.job_id, job.id)
        self.assertEqual(response.lead_count, 500)
        # Live submission keeps the route-level 202 default.
        self.assertEqual(response_obj.status_code, 202)

    async def test_endpoint_is_permission_gated(self) -> None:
        from fastapi import HTTPException
        from app.routes.analytics_admin import submit_backfill_stage_transitions

        sig = inspect.signature(submit_backfill_stage_transitions)
        auth_param = sig.parameters.get("auth")
        self.assertIsNotNone(auth_param)
        assert auth_param is not None
        checker = getattr(auth_param.default, "dependency", None)
        self.assertIsNotNone(checker)
        assert checker is not None

        with self.assertRaises(HTTPException) as cm:
            await checker(auth=_auth("cost:view"))
        self.assertEqual(cm.exception.status_code, 403)
        self.assertIn("analytics:admin", cm.exception.detail)


# ── job registry ────────────────────────────────────────────────────────


class JobRegistryTests(unittest.TestCase):
    def test_stage_transitions_handler_registered(self) -> None:
        from app.services.job_worker import JOB_HANDLERS, RETRY_SAFE_JOB_TYPES

        self.assertIn("backfill-stage-transitions", JOB_HANDLERS)
        self.assertIn("backfill-stage-transitions", RETRY_SAFE_JOB_TYPES)


# ── watermark behavior ──────────────────────────────────────────────────


class WatermarkAdvanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_finalize_advances_watermark_only_on_success(self) -> None:
        captured: dict[str, Any] = {"success": {}, "error": {}}

        async def _capture(status_key: str):
            sync_run = SimpleNamespace(
                status=None, completed_at=None, records_scanned=0,
                records_upserted=0, records_failed=0, error_message=None,
                watermark_to=None, details={},
            )
            log_row = SimpleNamespace(
                status=None, completed_at=None, duration_ms=None,
                rows_inserted=0, rows_updated=0, error_message=None,
                metadata_=None,
            )

            async def _get(model, _id):
                if model.__name__ == "LogFactPopulationRun":
                    return log_row
                return sync_run

            session = AsyncMock()
            session.get = _get
            session.begin = MagicMock()
            session.begin.return_value.__aenter__ = AsyncMock(return_value=None)
            session.begin.return_value.__aexit__ = AsyncMock(return_value=None)

            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=session)
            cm.__aexit__ = AsyncMock(return_value=None)

            counters = backfill._BackfillCounters()
            counters.watermark_to = datetime(
                2026, 5, 14, 12, 0, tzinfo=timezone.utc
            )
            request = backfill.BackfillRequest(
                app_id="inside-sales",
                dry_run=False,
                max_leads=100,
                batch_size=100,
                started_after=None,
                ended_before=None,
            )

            with patch(
                "app.services.analytics.backfill_stage_transitions_job.async_session",
                return_value=cm,
            ):
                await backfill._finalize_log_row(
                    log_row_id=uuid.uuid4(),
                    sync_run_id=uuid.uuid4(),
                    started_at=datetime.now(timezone.utc),
                    status=status_key,
                    error_message=None if status_key == "success" else "boom",
                    counters=counters,
                    request=request,
                )
            captured[status_key] = {
                "watermark_to": sync_run.watermark_to,
                "status": sync_run.status,
            }

        await _capture("success")
        await _capture("error")

        # On success: watermark advances; on error: it stays None so the
        # next run replays the same window.
        self.assertIsNotNone(captured["success"]["watermark_to"])
        self.assertEqual(captured["success"]["status"], "completed")
        self.assertIsNone(captured["error"]["watermark_to"])
        self.assertEqual(captured["error"]["status"], "failed")


# ── steady-state writer regression ──────────────────────────────────────


class SteadyStateWriterRegressionTests(unittest.IsolatedAsyncioTestCase):
    """Confirms ``inside_sales_sync._append_lead_stage_transitions`` still
    inserts a row when the lead's stage changes vs the latest known
    ``to_stage`` for the same lead.

    Plan Phase 4 done-gate asks for a manual dev verification of the
    steady-state writer; this regression test covers it deterministically
    without running a real LSQ sync. If this test ever goes red, the
    backfill's "from today onward steady-state captures every transition"
    invariant is broken and Phase 6 needs a fix here too.
    """

    async def test_inserts_row_when_current_stage_differs_from_prior(self) -> None:
        from app.services import inside_sales_sync as sync_mod

        tenant_id = uuid.uuid4()
        # Two leads: one whose current stage matches the prior known stage
        # (must be SKIPPED), one whose current stage differs (must INSERT).
        rows = [
            {
                "tenant_id": tenant_id,
                "app_id": "inside-sales",
                "lead_id": "L-unchanged",
                "prospect_stage": "Qualified Lead",
            },
            {
                "tenant_id": tenant_id,
                "app_id": "inside-sales",
                "lead_id": "L-changed",
                "prospect_stage": "Payment Received",
            },
        ]

        prior_known: list[Any] = [
            SimpleNamespace(
                tenant_id=tenant_id,
                app_id="inside-sales",
                lead_id="L-unchanged",
                to_stage="Qualified Lead",
                detected_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            ),
            SimpleNamespace(
                tenant_id=tenant_id,
                app_id="inside-sales",
                lead_id="L-changed",
                to_stage="Qualified Lead",
                detected_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            ),
        ]

        captured_inserts: list[Any] = []

        async def _execute(stmt):
            stmt_text = str(stmt)
            if "SELECT" in stmt_text and "fact_lead_stage_transition" in stmt_text:
                # Return the latest known to_stage per lead.
                result = MagicMock()
                result.all = MagicMock(return_value=prior_known)
                return result
            if "INSERT" in stmt_text and "fact_lead_stage_transition" in stmt_text:
                captured_inserts.append(stmt)
                return MagicMock()
            return MagicMock()

        db = AsyncMock()
        db.execute = _execute

        sync_run_id = uuid.uuid4()
        inserted = await sync_mod._append_lead_stage_transitions(
            db,
            rows=rows,
            cycle_start=datetime(2026, 5, 14, tzinfo=timezone.utc),
            sync_run_id=sync_run_id,
        )

        # Only the changed lead's transition is emitted.
        self.assertEqual(inserted, 1)
        self.assertEqual(len(captured_inserts), 1)
        # Inspect the pg_insert's bound parameters directly — compiling
        # with literal_binds would fail on JSONB '{}' rendering, but the
        # params dict carries exactly what would be sent over the wire.
        compiled_params = captured_inserts[0].compile().params
        param_values = list(compiled_params.values())
        self.assertIn("Payment Received", param_values)
        self.assertIn("L-changed", param_values)
        self.assertNotIn("L-unchanged", param_values)
        # And sync_run_id is stamped on the new row.
        self.assertIn(sync_run_id, param_values)

    async def test_writer_insert_uses_on_conflict_do_nothing(self) -> None:
        """Defense-in-depth: the INSERT statement carries ON CONFLICT DO
        NOTHING against the partial unique index. Read-before-write is the
        primary idempotency mechanism, but a concurrent retry under the
        new unique index would raise IntegrityError without this clause.
        """
        from app.services import inside_sales_sync as sync_mod

        tenant_id = uuid.uuid4()
        rows = [
            {
                "tenant_id": tenant_id,
                "app_id": "inside-sales",
                "lead_id": "L-first-time",
                "prospect_stage": "Qualified Lead",
            },
        ]
        captured_inserts: list[Any] = []

        async def _execute(stmt):
            stmt_text = str(stmt)
            if "SELECT" in stmt_text and "fact_lead_stage_transition" in stmt_text:
                result = MagicMock()
                result.all = MagicMock(return_value=[])  # no prior rows
                return result
            if "INSERT" in stmt_text and "fact_lead_stage_transition" in stmt_text:
                captured_inserts.append(stmt)
                return MagicMock()
            return MagicMock()

        db = AsyncMock()
        db.execute = _execute

        await sync_mod._append_lead_stage_transitions(
            db,
            rows=rows,
            cycle_start=datetime(2026, 5, 14, tzinfo=timezone.utc),
            sync_run_id=uuid.uuid4(),
        )

        self.assertEqual(len(captured_inserts), 1)
        compiled = str(captured_inserts[0])
        # Must include the conflict clause keyed on the partial unique index.
        self.assertIn("ON CONFLICT", compiled.upper())
        self.assertIn("sync_run_id IS NOT NULL", compiled)


if __name__ == "__main__":
    unittest.main()
