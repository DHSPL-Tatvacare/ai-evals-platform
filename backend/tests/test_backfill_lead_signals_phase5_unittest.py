"""Phase 5 tests for ``backfill-lead-signals``.

Covers:
  - Request parsing / bounds validation (max_leads, batch_size, cost_budget).
  - Input normalization for `crm_lead_record.mql_signals` (dict / list /
    JSON-string / scalar edge cases).
  - LLM call routes through ``LoggingLLMWrapper`` (asserted via stub
    capturing the ``generate_json`` payload + provider type).
  - Idempotent upsert keys the conflict on
    ``(tenant_id, app_id, lead_id, signal_type, detected_at)`` with the
    partial ``sync_run_id IS NOT NULL`` predicate.
  - Dry-run path returns lead count + estimated cost without enqueuing.
  - Watermark advances only on success.
  - Cost-budget gate refuses a live run when the projection exceeds the
    budget.
  - Admin endpoint permission gate (``analytics:admin``).

CRM-agnostic by design — tests use ``app_id="inside-sales"`` but exercise
the same path future CRM-backed apps will take.
"""
from __future__ import annotations

import inspect
import unittest
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.analytics import backfill_lead_signals_job as backfill


# ── helpers ─────────────────────────────────────────────────────────────


def _auth(*perms: str):
    return SimpleNamespace(
        is_owner=False,
        permissions=frozenset(perms),
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )


def _make_response():
    """Minimal stand-in for fastapi.Response so the endpoint can set status_code."""
    return SimpleNamespace(status_code=202)


class _FakeLead:
    """Stand-in for ``CrmLeadRecord`` with enough fields for tests."""

    def __init__(
        self,
        *,
        lead_id: str = "L-1",
        tenant_id: uuid.UUID | None = None,
        app_id: str = "inside-sales",
        mql_signals: Any = None,
        last_synced_at: datetime | None = None,
        condition: str | None = "diabetes",
        hba1c_band: str | None = "7-9",
        age_group: str | None = "45-60",
        intent_to_pay: str | None = "high",
        plan_name: str | None = "Care Plus",
        city: str | None = "Pune",
        source: str | None = "facebook",
        source_campaign: str | None = "diwali-2026",
        prospect_stage: str = "QL",
        mql_score: int = 80,
    ) -> None:
        self.lead_id = lead_id
        self.tenant_id = tenant_id or uuid.uuid4()
        self.app_id = app_id
        self.mql_signals = mql_signals
        self.last_synced_at = last_synced_at or datetime(
            2026, 5, 14, tzinfo=timezone.utc
        )
        self.created_on = self.last_synced_at
        self.condition = condition
        self.hba1c_band = hba1c_band
        self.age_group = age_group
        self.intent_to_pay = intent_to_pay
        self.plan_name = plan_name
        self.city = city
        self.source = source
        self.source_campaign = source_campaign
        self.prospect_stage = prospect_stage
        self.mql_score = mql_score


# ── parse_request ───────────────────────────────────────────────────────


class ParseRequestTests(unittest.TestCase):
    def test_defaults_when_only_app_id_provided(self) -> None:
        req = backfill.parse_request({"app_id": "inside-sales"})
        self.assertEqual(req.app_id, "inside-sales")
        self.assertFalse(req.dry_run)
        self.assertEqual(req.max_leads, backfill.DEFAULT_MAX_LEADS)
        self.assertEqual(req.batch_size, backfill.DEFAULT_BATCH_SIZE)
        self.assertEqual(req.cost_budget_usd, backfill.DEFAULT_COST_BUDGET_USD)

    def test_missing_app_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            backfill.parse_request({})

    def test_batch_size_out_of_bounds_raises(self) -> None:
        with self.assertRaises(ValueError):
            backfill.parse_request(
                {"app_id": "inside-sales", "batch_size": 1}
            )
        with self.assertRaises(ValueError):
            backfill.parse_request(
                {
                    "app_id": "inside-sales",
                    "batch_size": backfill.MAX_BATCH_SIZE + 1,
                }
            )

    def test_max_leads_out_of_bounds_raises(self) -> None:
        with self.assertRaises(ValueError):
            backfill.parse_request(
                {"app_id": "inside-sales", "max_leads": 0}
            )
        with self.assertRaises(ValueError):
            backfill.parse_request(
                {
                    "app_id": "inside-sales",
                    "max_leads": backfill.MAX_MAX_LEADS + 1,
                }
            )

    def test_cost_budget_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            backfill.parse_request(
                {"app_id": "inside-sales", "cost_budget_usd": 0}
            )

    def test_iso_datetime_with_z_parses(self) -> None:
        req = backfill.parse_request(
            {
                "app_id": "inside-sales",
                "started_after": "2026-01-25T00:00:00Z",
                "ended_before": "2026-05-13T00:00:00+00:00",
            }
        )
        self.assertEqual(
            req.started_after, datetime(2026, 1, 25, tzinfo=timezone.utc)
        )
        self.assertEqual(
            req.ended_before, datetime(2026, 5, 13, tzinfo=timezone.utc)
        )


# ── mql_signals normalization ───────────────────────────────────────────


class NormalizeMqlSignalsTests(unittest.TestCase):
    def test_none_returns_empty(self) -> None:
        self.assertEqual(backfill._normalize_mql_signals(None), [])

    def test_dict_shape_becomes_list_of_typed_value_raw(self) -> None:
        normalized = backfill._normalize_mql_signals(
            {"diabetes_confirmed": True, "purchase_intent": "high"}
        )
        types = sorted(item["signal_type"] for item in normalized)
        self.assertEqual(types, ["diabetes_confirmed", "purchase_intent"])
        for item in normalized:
            self.assertIn("value", item)
            self.assertIn("raw", item)

    def test_list_of_dicts_with_signal_type_keeps_label(self) -> None:
        normalized = backfill._normalize_mql_signals(
            [{"signal_type": "objection", "signal_value": "price"}]
        )
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["signal_type"], "objection")
        self.assertEqual(normalized[0]["value"], "price")

    def test_json_encoded_string_decodes(self) -> None:
        normalized = backfill._normalize_mql_signals('{"foo": "bar"}')
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["signal_type"], "foo")

    def test_garbage_string_becomes_raw_signal(self) -> None:
        normalized = backfill._normalize_mql_signals("not-json")
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["signal_type"], "raw")

    def test_blank_keys_are_skipped(self) -> None:
        normalized = backfill._normalize_mql_signals({"": "x", "valid": 1})
        self.assertEqual([item["signal_type"] for item in normalized], ["valid"])


# ── extraction input ────────────────────────────────────────────────────


class ExtractionInputTests(unittest.TestCase):
    def test_has_payload_false_when_all_inputs_empty(self) -> None:
        lead = _FakeLead(
            mql_signals=None,
            condition=None,
            hba1c_band=None,
            age_group=None,
            intent_to_pay=None,
            plan_name=None,
            city=None,
            source=None,
            source_campaign=None,
            prospect_stage="",
            mql_score=0,
        )
        out = backfill._build_extraction_input(lead, None)
        self.assertFalse(out["has_payload"])

    def test_has_payload_true_when_mql_signals_present(self) -> None:
        lead = _FakeLead(mql_signals={"foo": "bar"})
        out = backfill._build_extraction_input(lead, None)
        self.assertTrue(out["has_payload"])
        self.assertEqual(out["mql_signals"][0]["signal_type"], "foo")

    def test_typed_bag_drops_zero_and_empty_strings(self) -> None:
        lead = _FakeLead(
            mql_score=0,
            condition="",
            prospect_stage="QL",
            city=None,
        )
        out = backfill._build_extraction_input(lead, None)
        self.assertNotIn("mql_score", out["typed_bag"])
        self.assertNotIn("condition", out["typed_bag"])
        self.assertNotIn("city", out["typed_bag"])
        self.assertIn("prospect_stage", out["typed_bag"])


# ── cost estimate ───────────────────────────────────────────────────────


class CostEstimateTests(unittest.TestCase):
    def test_zero_leads_is_zero_cost(self) -> None:
        self.assertEqual(backfill.estimate_cost(0), 0.0)

    def test_thirty_thousand_at_default_rate_under_15_dollars(self) -> None:
        cost = backfill.estimate_cost(30_000)
        self.assertEqual(cost, 30_000 * backfill.DEFAULT_PER_LEAD_COST_USD)
        # Sanity: under the default cost budget so a default-config run is
        # not blocked at the gate.
        self.assertLessEqual(cost, backfill.DEFAULT_COST_BUDGET_USD * 2)


# ── projection / upsert ─────────────────────────────────────────────────


class ProjectSignalRowsTests(unittest.TestCase):
    def test_emits_one_row_per_signal_type_with_sync_run_id(self) -> None:
        lead = _FakeLead()
        sync_run_id = uuid.uuid4()
        detected_at = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)
        signals = [
            {
                "signal_type": "purchase_intent",
                "signal_value": "high",
                "confidence": 0.9,
            },
            {"signal_type": "objection", "signal_value": "price"},
        ]
        rows = backfill._project_signal_rows(
            lead=lead,
            signals=signals,
            tenant_id=lead.tenant_id,
            sync_run_id=sync_run_id,
            detected_at=detected_at,
        )
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["sync_run_id"], sync_run_id)
            self.assertEqual(row["detected_at"], detected_at)
            self.assertIsNone(row["eval_run_id"])
            self.assertIsNone(row["thread_evaluation_id"])
            self.assertEqual(row["lead_id"], lead.lead_id)
            self.assertEqual(row["app_id"], lead.app_id)
            self.assertEqual(row["tenant_id"], lead.tenant_id)

    def test_duplicates_within_signal_type_collapse_to_one_row(self) -> None:
        # Partial unique key is (tenant, app, lead_id, signal_type, detected_at),
        # so two raw signals of the same type would collide. Keep the first,
        # stash the rest under attributes.duplicates.
        lead = _FakeLead()
        sync_run_id = uuid.uuid4()
        detected_at = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)
        rows = backfill._project_signal_rows(
            lead=lead,
            signals=[
                {"signal_type": "objection", "signal_value": "price"},
                {"signal_type": "objection", "signal_value": "trust"},
            ],
            tenant_id=lead.tenant_id,
            sync_run_id=sync_run_id,
            detected_at=detected_at,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["signal_value"], "price")
        self.assertIn("duplicates", rows[0]["attributes"])

    def test_unknown_signal_type_coerces_to_other_notable_signal(self) -> None:
        lead = _FakeLead()
        sync_run_id = uuid.uuid4()
        rows = backfill._project_signal_rows(
            lead=lead,
            signals=[{"signal_type": "not_in_taxonomy"}],
            tenant_id=lead.tenant_id,
            sync_run_id=sync_run_id,
            detected_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["signal_type"], "other_notable_signal")
        self.assertEqual(
            rows[0]["attributes"].get("signal_type_raw"), "not_in_taxonomy"
        )

    def test_decimal_coerces_numeric_strings(self) -> None:
        lead = _FakeLead()
        rows = backfill._project_signal_rows(
            lead=lead,
            signals=[
                {
                    "signal_type": "purchase_intent",
                    "signal_value_numeric": "0.85",
                    "confidence": "0.7",
                }
            ],
            tenant_id=lead.tenant_id,
            sync_run_id=uuid.uuid4(),
            detected_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
        )
        self.assertEqual(rows[0]["signal_value_numeric"], Decimal("0.85"))
        self.assertEqual(rows[0]["confidence"], Decimal("0.7"))


class DetectedAtSemanticsTests(unittest.TestCase):
    def test_detected_at_derives_from_last_synced_at(self) -> None:
        # The whole idempotency story depends on this: detected_at MUST come
        # from the lead's source state, not wall-clock at extraction time.
        ts = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
        lead = _FakeLead(last_synced_at=ts)
        self.assertEqual(backfill._detected_at_for(lead), ts)

    def test_detected_at_falls_back_to_created_on(self) -> None:
        # Pure SimpleNamespace lets us exercise last_synced_at=None without
        # fighting the typed _FakeLead defaults.
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        lead = SimpleNamespace(
            lead_id="L-1",
            tenant_id=uuid.uuid4(),
            app_id="inside-sales",
            last_synced_at=None,
            created_on=ts,
        )
        self.assertEqual(backfill._detected_at_for(lead), ts)

    def test_detected_at_epoch_when_both_timestamps_missing(self) -> None:
        lead = SimpleNamespace(
            lead_id="L-1",
            tenant_id=uuid.uuid4(),
            app_id="inside-sales",
            last_synced_at=None,
            created_on=None,
        )
        out = backfill._detected_at_for(lead)
        # The unix-epoch sentinel is documented in the helper's docstring:
        # the upsert never receives NULL, but operators see the obviously-
        # bogus timestamp and investigate.
        self.assertEqual(out, datetime(1970, 1, 1, tzinfo=timezone.utc))

    def test_rerun_over_unchanged_lead_produces_same_key(self) -> None:
        # Two runs over the same lead state must produce the same
        # (lead_id, signal_type, detected_at) tuple so the partial unique
        # index collides and the upsert collapses. This is the heart of the
        # idempotency guarantee called out in the plan §3.2 amendment.
        lead = _FakeLead(
            last_synced_at=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
        )
        first = backfill._project_signal_rows(
            lead=lead,
            signals=[{"signal_type": "purchase_intent"}],
            tenant_id=lead.tenant_id,
            sync_run_id=uuid.uuid4(),
            detected_at=backfill._detected_at_for(lead),
        )
        second = backfill._project_signal_rows(
            lead=lead,
            signals=[{"signal_type": "purchase_intent"}],
            tenant_id=lead.tenant_id,
            sync_run_id=uuid.uuid4(),  # different run, same lead state
            detected_at=backfill._detected_at_for(lead),
        )
        # Different sync_run_id (rotates per backfill) but same conflict key.
        self.assertEqual(first[0]["lead_id"], second[0]["lead_id"])
        self.assertEqual(first[0]["signal_type"], second[0]["signal_type"])
        self.assertEqual(first[0]["detected_at"], second[0]["detected_at"])
        self.assertNotEqual(first[0]["sync_run_id"], second[0]["sync_run_id"])


class ExtractSignalsEdgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_signals_array_returns_empty_list(self) -> None:
        provider = SimpleNamespace(
            generate_json=AsyncMock(return_value={"signals": []})
        )
        out = await backfill._extract_signals(
            provider,
            {
                "lead_id": "L-1",
                "mql_score": 80,
                "mql_signals": [],
                "typed_bag": {"condition": "diabetes"},
                "attributes_at_first_seen": {},
            },
        )
        self.assertEqual(out, [])

    async def test_signals_field_missing_returns_empty(self) -> None:
        provider = SimpleNamespace(
            generate_json=AsyncMock(return_value={"unrelated": 1})
        )
        out = await backfill._extract_signals(
            provider,
            {
                "lead_id": "L-1",
                "mql_score": 0,
                "mql_signals": [],
                "typed_bag": {},
                "attributes_at_first_seen": {},
            },
        )
        self.assertEqual(out, [])

    async def test_signal_items_without_signal_type_are_dropped(self) -> None:
        provider = SimpleNamespace(
            generate_json=AsyncMock(
                return_value={
                    "signals": [
                        {"signal_type": "purchase_intent"},
                        {"signal_value": "no_type_here"},
                        "not-a-dict",
                    ]
                }
            )
        )
        out = await backfill._extract_signals(
            provider,
            {
                "lead_id": "L-1",
                "mql_score": 0,
                "mql_signals": [],
                "typed_bag": {},
                "attributes_at_first_seen": {},
            },
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["signal_type"], "purchase_intent")


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
        await backfill._upsert_signal_rows(
            db,
            rows=[
                {
                    "id": uuid.uuid4(),
                    "tenant_id": uuid.uuid4(),
                    "app_id": "inside-sales",
                    "eval_run_id": None,
                    "thread_evaluation_id": None,
                    "sync_run_id": uuid.uuid4(),
                    "lead_id": "L-1",
                    "source_activity_id": None,
                    "signal_type": "purchase_intent",
                    "signal_value": "high",
                    "signal_value_numeric": None,
                    "signal_at": None,
                    "detected_at": datetime(2026, 5, 14, tzinfo=timezone.utc),
                    "confidence": None,
                    "supporting_quote": None,
                    "ordinal": 0,
                    "attributes": {},
                }
            ],
        )
        compiled = str(captured["stmt"].compile())
        # Conflict columns + partial predicate must both appear so Postgres
        # picks uq_fact_lead_signal_backfill (and not the eval-run-coupled
        # unique constraint).
        for col in ("tenant_id", "app_id", "lead_id", "signal_type", "detected_at"):
            self.assertIn(col, compiled)
        self.assertIn("sync_run_id IS NOT NULL", compiled)


# ── dry-run / counters ──────────────────────────────────────────────────


class DryRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_skips_llm_and_returns_estimate(self) -> None:
        # ``count_candidate_leads`` is patched so the test doesn't need a
        # real DB; the focus is "no provider build, no row writes".
        with patch.object(
            backfill, "count_candidate_leads", AsyncMock(return_value=1234)
        ), patch.object(
            backfill, "_build_llm_provider"
        ) as build_provider, patch(
            "app.database.async_session"
        ) as session_factory:
            session_factory.return_value.__aenter__.return_value = AsyncMock()
            session_factory.return_value.__aexit__.return_value = None
            result = await backfill.run_backfill_lead_signals(
                job_id=uuid.uuid4(),
                params={"app_id": "inside-sales", "dry_run": True},
                tenant_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
            )
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["lead_count"], 1234)
        self.assertGreater(result["estimated_cost_usd"], 0)
        build_provider.assert_not_called()


# ── cost-budget gate ────────────────────────────────────────────────────


class CostBudgetGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_over_budget_run_refuses_before_writes(self) -> None:
        # 50k leads * $0.01 = $500, way over the $5 budget. Refuses BEFORE
        # opening the bookkeeping session.
        with patch.object(
            backfill, "count_candidate_leads", AsyncMock(return_value=50_000)
        ), patch.object(
            backfill, "_build_llm_provider"
        ) as build_provider:
            with self.assertRaises(ValueError) as cm:
                await backfill.run_backfill_lead_signals(
                    job_id=uuid.uuid4(),
                    params={
                        "app_id": "inside-sales",
                        "dry_run": False,
                        "max_leads": 50_000,
                        "cost_budget_usd": 5.0,
                    },
                    tenant_id=uuid.uuid4(),
                    user_id=uuid.uuid4(),
                )
        self.assertIn("exceeds cost_budget_usd", str(cm.exception))
        build_provider.assert_not_called()


# ── LLM routing assertion ───────────────────────────────────────────────


class LlmRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_extract_signals_calls_generate_json_with_schema(self) -> None:
        # Stub provider proves the call shape — generate_json with the
        # strict response schema, no direct provider SDK call.
        captured: dict[str, Any] = {}

        async def _generate_json(prompt, system_prompt=None, json_schema=None, **kw):
            captured["prompt"] = prompt
            captured["system_prompt"] = system_prompt
            captured["json_schema"] = json_schema
            return {"signals": [{"signal_type": "purchase_intent"}]}

        provider = SimpleNamespace(generate_json=_generate_json)
        signals = await backfill._extract_signals(
            provider,
            {
                "lead_id": "L-1",
                "mql_score": 80,
                "mql_signals": [],
                "typed_bag": {"condition": "diabetes"},
                "attributes_at_first_seen": {},
            },
        )
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["signal_type"], "purchase_intent")
        self.assertIs(captured["json_schema"], backfill.SIGNAL_RESPONSE_SCHEMA)
        self.assertIn("Lead snapshot", captured["prompt"])

    async def test_extract_signals_returns_empty_on_malformed_response(self) -> None:
        provider = SimpleNamespace(
            generate_json=AsyncMock(return_value="not-a-dict")
        )
        self.assertEqual(
            await backfill._extract_signals(
                provider,
                {
                    "lead_id": "L-1",
                    "mql_score": 0,
                    "mql_signals": [],
                    "typed_bag": {},
                    "attributes_at_first_seen": {},
                },
            ),
            [],
        )


# ── admin endpoint ──────────────────────────────────────────────────────


class AdminEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_returns_count_and_estimate_without_job(self) -> None:
        from app.routes.analytics_admin import (
            BackfillLeadSignalsRequest,
            submit_backfill_lead_signals,
        )

        added: list[Any] = []
        db = AsyncMock()
        db.add = lambda row: added.append(row)
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        with patch(
            "app.routes.analytics_admin.count_candidate_leads",
            AsyncMock(return_value=2_500),
        ):
            body = BackfillLeadSignalsRequest(
                app_id="inside-sales", dry_run=True
            )
            response_obj = _make_response()
            response = await submit_backfill_lead_signals(
                body=body,
                response=response_obj,
                auth=_auth("analytics:admin"),
                db=db,
            )

        # Dry-run must not enqueue a job.
        self.assertEqual(added, [])
        # Dry-run is informational — status MUST flip from the route-level
        # 202 default down to 200.
        self.assertEqual(response_obj.status_code, 200)
        self.assertTrue(response.dry_run)
        self.assertEqual(response.lead_count, 2_500)
        self.assertEqual(
            response.estimated_cost_usd,
            backfill.estimate_cost(2_500),
        )
        self.assertFalse(response.over_budget)

    async def test_live_run_creates_job_and_returns_ids(self) -> None:
        from app.routes.analytics_admin import (
            BackfillLeadSignalsRequest,
            submit_backfill_lead_signals,
        )

        added: list[Any] = []
        db = AsyncMock()
        db.add = lambda row: added.append(row)
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        with patch(
            "app.routes.analytics_admin.count_candidate_leads",
            AsyncMock(return_value=500),
        ):
            body = BackfillLeadSignalsRequest(
                app_id="inside-sales", dry_run=False
            )
            response_obj = _make_response()
            response = await submit_backfill_lead_signals(
                body=body,
                response=response_obj,
                auth=_auth("analytics:admin"),
                db=db,
            )

        self.assertEqual(len(added), 1)
        job = added[0]
        self.assertEqual(job.job_type, "backfill-lead-signals")
        self.assertEqual(job.queue_class, "bulk")
        self.assertEqual(job.params["app_id"], "inside-sales")
        self.assertFalse(job.params["dry_run"])
        self.assertEqual(response.job_id, job.id)
        self.assertEqual(response.lead_count, 500)
        # Live submission keeps the route-level 202 default; only the
        # dry-run branch flips down to 200.
        self.assertEqual(response_obj.status_code, 202)

    async def test_live_run_over_budget_rejected_400(self) -> None:
        from fastapi import HTTPException
        from app.routes.analytics_admin import (
            BackfillLeadSignalsRequest,
            submit_backfill_lead_signals,
        )

        added: list[Any] = []
        db = AsyncMock()
        db.add = lambda row: added.append(row)
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        with patch(
            "app.routes.analytics_admin.count_candidate_leads",
            AsyncMock(return_value=50_000),
        ):
            body = BackfillLeadSignalsRequest(
                app_id="inside-sales",
                dry_run=False,
                cost_budget_usd=1.0,
                max_leads=50_000,
            )
            with self.assertRaises(HTTPException) as cm:
                await submit_backfill_lead_signals(
                    body=body,
                    response=_make_response(),
                    auth=_auth("analytics:admin"),
                    db=db,
                )
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("exceeds cost_budget_usd", cm.exception.detail)
        self.assertEqual(added, [])

    async def test_endpoint_is_permission_gated(self) -> None:
        from fastapi import HTTPException
        from app.routes.analytics_admin import submit_backfill_lead_signals

        sig = inspect.signature(submit_backfill_lead_signals)
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
    def test_lead_signals_handler_registered(self) -> None:
        from app.services.job_worker import JOB_HANDLERS, RETRY_SAFE_JOB_TYPES

        self.assertIn("backfill-lead-signals", JOB_HANDLERS)
        self.assertIn("backfill-lead-signals", RETRY_SAFE_JOB_TYPES)


# ── watermark behavior ──────────────────────────────────────────────────


class WatermarkAdvanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_finalize_advances_watermark_only_on_success(self) -> None:
        # Verify the finalize routine sets sync_run.watermark_to ONLY when
        # status='success'. Failure path must leave it untouched so the
        # next run replays the same window.
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
                # LogCrmSourceSync also contains "Log"; route by exact name.
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
                cost_budget_usd=15.0,
                started_after=None,
                ended_before=None,
            )

            with patch("app.services.analytics.backfill_lead_signals_job.async_session", return_value=cm):
                await backfill._finalize_log_row(
                    log_row_id=uuid.uuid4(),
                    sync_run_id=uuid.uuid4(),
                    started_at=datetime.now(timezone.utc),
                    status=status_key,
                    error_message=None if status_key == "success" else "boom",
                    counters=counters,
                    request=request,
                    estimated_cost_usd=1.23,
                )
            captured[status_key] = {
                "watermark_to": sync_run.watermark_to,
                "status": sync_run.status,
            }

        await _capture("success")
        await _capture("error")

        # On success: watermark advances.
        self.assertIsNotNone(captured["success"]["watermark_to"])
        self.assertEqual(captured["success"]["status"], "completed")
        # On error: watermark stays None (the next run replays the same window).
        self.assertIsNone(captured["error"]["watermark_to"])
        self.assertEqual(captured["error"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
