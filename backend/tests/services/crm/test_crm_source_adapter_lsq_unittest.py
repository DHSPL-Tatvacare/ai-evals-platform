"""LSQ CRM-source adapter — land + discover only, against VERBATIM LSQ shapes.

Fixtures are the captured LSQ lead/activity shapes (design doc Appendix A). No
live LSQ call: the adapter takes an injectable transport so the HTTP seam is
faked. The adapter NEVER shapes a serving row — it only drafts landing records
and discovers fields.
"""
from __future__ import annotations

import asyncio
import unittest
from typing import Any

from app.services.crm.adapters import resolve_crm_adapter
from app.services.crm.adapters.lsq import (
    LsqCrmSourceAdapter,
    lsq_activity_draft,
    lsq_lead_draft,
)
from app.services.crm.adapters.protocol import (
    DiscoveredObject,
    FetchPage,
    SourceRecordDraft,
)

# --- VERBATIM LSQ shapes (Appendix A keys) -------------------------------------------------
LSQ_LEAD: dict[str, Any] = {
    "ProspectID": "a1b2c3",
    "FirstName": "Asha",
    "LastName": "Rao",
    "Phone": "9876543210",
    "EmailAddress": "asha@example.com",
    "ProspectStage": "Interested",
    "Source": "Facebook",
    "SourceCampaign": "diab-2025",
    "OwnerIdName": "Rep One",
    "CreatedOn": "2025-01-15 10:30:00",
    "ModifiedOn": "2025-02-01 14:00:00",
    "ProspectActivityDate_Min": "2025-01-15 10:35:00",
    "ProspectActivityDate_Max": "2025-02-01 14:00:00",
    "LeadConversionDate": "",
    "mx_City": "Pune",
    "mx_Age_Group": "35-44",
    "mx_utm_disease": "Diabetes",
    "mx_Do_you_remember_your_HbA1c_levels": "7-8",
    "mx_Plan_Name": "Premium",
}

LSQ_ACTIVITY: dict[str, Any] = {
    "ProspectActivityId": "act-991",
    "RelatedProspectId": "a1b2c3",
    "ActivityEvent": 22,
    "CreatedBy": "u-1",
    "CreatedByName": "Rep One",
    "CreatedByEmailAddress": "rep1@example.com",
    "Status": "Answered",
    "mx_Custom_1": "+918001234567",
    "mx_Custom_2": "2025-01-16 11:00:00",
    "mx_Custom_3": "182",
    "mx_Custom_4": "https://rec.example/abc.mp3",
    "ActivityEvent_Note": 'note SourceData {"SourceNumber":"x","CallNotes":"ok"}',
    "CreatedOn": "2025-01-16 11:03:00",
}


class _FakeTransport:
    """Records calls; returns verbatim fixtures keyed by path + event code."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def post(
        self, *, base_url: str, path: str, params: dict[str, str], json: dict[str, Any]
    ) -> Any:
        self.calls.append({"base_url": base_url, "path": path, "params": params, "json": json})
        if path.endswith("Leads.Get"):
            return [LSQ_LEAD]
        if path.endswith("RetrieveByActivityEvent"):
            event = json.get("Parameter", {}).get("ActivityEvent")
            return {"List": [LSQ_ACTIVITY], "RecordCount": 1} if event == 22 else {"List": [], "RecordCount": 0}
        raise AssertionError(f"unexpected path {path}")


CREDS = {"region_host": "https://api-in21.leadsquared.com/v2", "access_key": "ak", "secret_key": "sk"}


def _run(coro):
    return asyncio.run(coro)


class TestLsqDrafts(unittest.TestCase):
    def test_lead_draft_is_landing_shaped(self):
        draft = lsq_lead_draft(LSQ_LEAD)
        self.assertIsInstance(draft, SourceRecordDraft)
        self.assertEqual(draft.source_object, "Lead")
        self.assertEqual(draft.record_type, "lead")
        self.assertEqual(draft.source_record_id, "a1b2c3")
        self.assertEqual(draft.raw_payload, LSQ_LEAD)

    def test_activity_draft_is_landing_shaped(self):
        draft = lsq_activity_draft(LSQ_ACTIVITY)
        self.assertEqual(draft.source_object, "Activity")
        self.assertEqual(draft.record_type, "activity")
        self.assertEqual(draft.source_record_id, "act-991")
        self.assertEqual(draft.raw_payload, LSQ_ACTIVITY)


class TestLsqAdapterRegistered(unittest.TestCase):
    def test_registered_under_crm_source_lsq(self):
        adapter = resolve_crm_adapter(vendor="lsq")
        self.assertEqual(adapter.capability, "crm_source")
        self.assertEqual(adapter.vendor, "lsq")


class TestLsqDiscover(unittest.TestCase):
    def test_discovers_both_grains_with_fields_from_sample(self):
        adapter = LsqCrmSourceAdapter(transport=_FakeTransport())
        objects = _run(adapter.discover_objects(creds=CREDS, sample_size=10))
        by_grain = {o.record_type: o for o in objects}
        self.assertIsInstance(objects[0], DiscoveredObject)
        self.assertEqual(set(by_grain), {"lead", "activity"})
        self.assertIn("ProspectID", by_grain["lead"].fields)
        self.assertIn("mx_utm_disease", by_grain["lead"].fields)
        self.assertIn("ProspectActivityId", by_grain["activity"].fields)
        self.assertIn("mx_Custom_3", by_grain["activity"].fields)


class TestLsqFetch(unittest.TestCase):
    def test_fetch_leads_returns_drafts_and_auths_by_query_params(self):
        transport = _FakeTransport()
        adapter = LsqCrmSourceAdapter(transport=transport)
        page = _run(adapter.fetch_records(creds=CREDS, source_object="Lead", watermark=None))
        self.assertIsInstance(page, FetchPage)
        self.assertEqual([d.source_record_id for d in page.records], ["a1b2c3"])
        self.assertEqual(page.records[0].record_type, "lead")
        call = transport.calls[0]
        self.assertEqual(call["base_url"], CREDS["region_host"])
        self.assertEqual(call["params"], {"accessKey": "ak", "secretKey": "sk"})

    def test_fetch_activities_sweeps_event_codes(self):
        transport = _FakeTransport()
        adapter = LsqCrmSourceAdapter(transport=transport)
        page = _run(adapter.fetch_records(creds=CREDS, source_object="Activity", watermark=None))
        self.assertEqual([d.source_record_id for d in page.records], ["act-991"])
        self.assertEqual(page.records[0].record_type, "activity")
        events = {c["json"].get("Parameter", {}).get("ActivityEvent") for c in transport.calls}
        self.assertEqual(events, {21, 22})


if __name__ == "__main__":
    unittest.main()
