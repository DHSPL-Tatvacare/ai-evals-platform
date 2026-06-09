"""LSQ source-ingestion adapter — filter capabilities, sampled field values, sample, pushdown.

All against VERBATIM LSQ shapes via an injectable transport — never a live call. LSQ is
read-only (no write, no distinct-values API): field values are sample-derived from a fetched
page, and only the narrow ``Leads.Get`` ``Parameter``/``SqlOperator`` lookup is server-pushable.
"""
from __future__ import annotations

import asyncio
import unittest
from typing import Any

from app.services.crm.adapters.lsq import LsqCrmSourceAdapter
from app.services.crm.adapters.protocol import FilterCapability, SourceRecordDraft

LSQ_LEAD_A: dict[str, Any] = {
    "ProspectID": "a1",
    "ProspectStage": "Interested",
    "OwnerIdName": "Rep One",
    "ModifiedOn": "2025-02-01 14:00:00",
    "mx_City": "Pune",
}
LSQ_LEAD_B: dict[str, Any] = {
    "ProspectID": "a2",
    "ProspectStage": "New",
    "OwnerIdName": "Rep Two",
    "ModifiedOn": "2025-02-02 09:00:00",
    "mx_City": "Mumbai",
}
LSQ_LEAD_C: dict[str, Any] = {
    "ProspectID": "a3",
    "ProspectStage": "Interested",
    "OwnerIdName": "Rep One",
    "ModifiedOn": "2025-02-03 09:00:00",
    "mx_City": "Pune",
}


class _FakeTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def post(
        self, *, base_url: str, path: str, params: dict[str, str], json: dict[str, Any]
    ) -> Any:
        self.calls.append({"base_url": base_url, "path": path, "params": params, "json": json})
        if path.endswith("Leads.Get"):
            return [LSQ_LEAD_A, LSQ_LEAD_B, LSQ_LEAD_C]
        raise AssertionError(f"unexpected path {path}")


CREDS = {"region_host": "https://api-in21.leadsquared.com/v2", "access_key": "ak", "secret_key": "sk"}


def _run(coro):
    return asyncio.run(coro)


class TestFilterCapabilities(unittest.TestCase):
    def test_lead_capabilities_are_honest_about_pushdown(self):
        adapter = LsqCrmSourceAdapter()
        cap = adapter.filter_capabilities("Lead")
        self.assertIsInstance(cap, FilterCapability)
        self.assertEqual(cap.source_object, "Lead")
        by_field = {f.field: f for f in cap.fields}
        # ModifiedOn is the one server-pushable date range.
        self.assertIn("ModifiedOn", by_field)
        self.assertTrue(by_field["ModifiedOn"].pushable)
        self.assertEqual(set(by_field["ModifiedOn"].operators), {"gte", "lte"})
        # A stage/owner lookup is pushable as eq/in.
        self.assertIn("ProspectStage", by_field)
        self.assertTrue(by_field["ProspectStage"].pushable)
        self.assertEqual(set(by_field["ProspectStage"].operators), {"eq", "in"})
        # Everything else is local-only.
        self.assertIn("mx_City", by_field)
        self.assertFalse(by_field["mx_City"].pushable)


class TestFieldValuesSampled(unittest.TestCase):
    def test_distinct_values_from_sample_page_deduped_sorted_capped(self):
        adapter = LsqCrmSourceAdapter(transport=_FakeTransport())
        values = _run(
            adapter.field_values(creds=CREDS, source_object="Lead", field="ProspectStage")
        )
        self.assertEqual(values, ["Interested", "New"])

    def test_limit_caps_returned_values(self):
        adapter = LsqCrmSourceAdapter(transport=_FakeTransport())
        values = _run(
            adapter.field_values(creds=CREDS, source_object="Lead", field="OwnerIdName", limit=1)
        )
        self.assertEqual(len(values), 1)


class TestSampleRecords(unittest.TestCase):
    def test_sample_records_returns_small_draft_sample(self):
        adapter = LsqCrmSourceAdapter(transport=_FakeTransport())
        sample = _run(adapter.sample_records(creds=CREDS, source_object="Lead", limit=2))
        self.assertTrue(all(isinstance(r, SourceRecordDraft) for r in sample))
        self.assertEqual([r.source_record_id for r in sample], ["a1", "a2"])


class TestFetchRecordsPushdown(unittest.TestCase):
    def test_pushable_leaf_lands_in_request_body(self):
        transport = _FakeTransport()
        adapter = LsqCrmSourceAdapter(transport=transport)
        predicate = {"field": "ModifiedOn", "op": "gte", "value": "2025-02-02 00:00:00"}
        _run(adapter.fetch_records(creds=CREDS, source_object="Lead", predicate=predicate))
        body = transport.calls[0]["json"]
        self.assertEqual(body["Parameter"]["LookupName"], "ModifiedOn")
        self.assertEqual(body["Parameter"]["LookupValue"], "2025-02-02 00:00:00")
        self.assertEqual(body["Parameter"]["SqlOperator"], ">=")

    def test_non_pushable_leaf_does_not_alter_body(self):
        transport = _FakeTransport()
        adapter = LsqCrmSourceAdapter(transport=transport)
        predicate = {"field": "mx_City", "op": "eq", "value": "Pune"}
        _run(adapter.fetch_records(creds=CREDS, source_object="Lead", predicate=predicate))
        body = transport.calls[0]["json"]
        # Non-pushable leaf is left for resolve-time; the default watermark lookup is untouched.
        self.assertEqual(body["Parameter"]["LookupName"], "ModifiedOn")
        self.assertNotEqual(body["Parameter"]["LookupValue"], "Pune")


if __name__ == "__main__":
    unittest.main()
