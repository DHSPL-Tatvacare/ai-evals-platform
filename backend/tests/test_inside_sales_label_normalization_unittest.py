"""Source-side normalization of filter-facing free-text labels.

LSQ sends rep / city / stage / condition / plan with stray trailing or double
spaces, which split one real value into duplicate filter entries. The sync must
clean these at write time (trim + collapse internal whitespace, preserve case).
IDs / phone / enums / numerics are intentionally left untouched.

Pure unit tests over the row builders — no DB, no LSQ.
"""
from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timezone

import app.services.inside_sales_sync as sync_service
import app.services.lsq_client as lsq_client

_TENANT = uuid.uuid4()
_USER = uuid.uuid4()
_SYNCED = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)


def _raw_call(created_by_name: str) -> dict:
    return {
        "ProspectActivityId": "activity-1",
        "RelatedProspectId": "prospect-1",
        "CreatedBy": "agent-1",
        "CreatedByName": created_by_name,
        "CreatedByEmailAddress": "amy@example.com",
        "ActivityEvent": 21,
        "Status": "Answered",
        "mx_Custom_2": "2026-04-08 09:00:00",
        "mx_Custom_3": "180",
        "mx_Custom_4": "https://example.com/recording.mp3",
        "mx_Custom_1": "Lead Amy",
        "ActivityEvent_Note": '{"SourceData":{"SourceNumber":"9999999999"}}',
        "CreatedOn": "2026-04-08 09:00:00",
    }


def _raw_lead(*, owner: str, city: str, stage: str = "New Lead", condition: str = "Diabetes") -> dict:
    return {
        "ProspectID": "prospect-1",
        "FirstName": "Lead",
        "LastName": "One",
        "Phone": "9999999999",
        "EmailAddress": "lead@example.com",
        "ProspectStage": stage,
        "mx_City": city,
        "mx_Age_Group": "31-40",
        "mx_utm_disease": condition,
        "mx_Do_you_remember_your_HbA1c_levels": "6.5",
        "mx_Are_you_open_to_investing_in_this_paid_program_of": "Yes",
        "mx_RNR_Count": "2",
        "mx_Answered_Call_Count": "3",
        "CreatedOn": "2026-04-01 09:00:00",
        "ProspectActivityDate_Min": "2026-04-01 10:00:00",
        "ProspectActivityDate_Max": "2026-04-07 10:00:00",
        "OwnerIdName": owner,
        "Source": "Campaign",
        "SourceCampaign": "April",
    }


class CleanLabelHelperTests(unittest.TestCase):
    def test_clean_label_trims_and_collapses_preserving_case(self):
        clean = lsq_client._clean_label
        self.assertEqual(clean("Madhu Priya "), "Madhu Priya")
        self.assertEqual(clean("  Madhu   Priya  "), "Madhu Priya")
        self.assertEqual(clean("Madhu Priya"), "Madhu Priya")  # case preserved
        self.assertIsNone(clean(None))
        self.assertIsNone(clean("   "))


class SourceLabelNormalizationTests(unittest.TestCase):
    def test_call_source_row_cleans_rep_name(self):
        row = sync_service.build_call_source_row(
            _raw_call(" Madhu  Priya "),
            tenant_id=_TENANT, user_id=_USER, app_id="inside-sales",
            source_system="lsq", synced_at=_SYNCED,
        )
        self.assertEqual(row["rep_name"], "Madhu Priya")

    def test_call_activity_fact_row_cleans_actor_label(self):
        fact = sync_service.build_call_activity_fact_row(
            _raw_call(" Madhu  Priya "),
            tenant_id=_TENANT, app_id="inside-sales", sync_run_id=None,
        )
        assert fact is not None
        self.assertEqual(fact["actor_label"], "Madhu Priya")

    def test_lead_source_row_cleans_rep_city_stage_condition(self):
        row = sync_service.build_lead_source_row(
            _raw_lead(owner=" Madhu  Priya ", city=" Mumbai ", stage=" New  Lead ",
                      condition=" Diabetes "),
            tenant_id=_TENANT, user_id=_USER, app_id="inside-sales",
            source_system="lsq", synced_at=_SYNCED,
        )
        assert row is not None
        self.assertEqual(row["city"], "Mumbai")
        raw = row["raw_payload"]
        self.assertEqual(raw["rep_name"], "Madhu Priya")
        self.assertEqual(raw["prospect_stage"], "New Lead")
        self.assertEqual(raw["condition"], "Diabetes")


if __name__ == "__main__":
    unittest.main()
