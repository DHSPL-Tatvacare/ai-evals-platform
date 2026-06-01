"""Task 6 — list_cohort_fields field-discovery for cohort sources.

Asserts the read-only field-discovery path reuses source_catalog +
the existing live introspection + the manifest PII flag, and never
invents a column, type, or PII tag.

PII fact (verified against the live manifest, not assumed): the manifest
catalog tables are keyed by the Sherlock-visible name (dim_lead,
fact_lead_activity, ...). NEITHER ``dim_patient`` NOR ``crm_lead_record``
is a manifest catalog table — ``crm_lead_record`` is a deliberately hidden
CRM mirror, and there is no ``dim_patient`` manifest table at all. So for
the two registered static sources the manifest PII lookup resolves to an
absent table and every field comes back pii=False. The pii FLAG is still
present and correct (False); the test asserts exactly that and the report
calls it out.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.orchestration_authoring.field_discovery import (
    CohortFieldRef,
    list_cohort_fields,
)


_CLINICAL_DESCRIPTOR = {
    "columns": [
        {"name": "first_name", "type": "string", "isJsonb": False},
        {"name": "primary_condition", "type": "string", "isJsonb": False},
        {"name": "hba1c_latest", "type": "number", "isJsonb": False},
        {"name": "active", "type": "boolean", "isJsonb": False},
        {"name": "last_visit_at", "type": "datetime", "isJsonb": False},
    ],
    "jsonb_keys": [],
}

_INTROSPECTED_DESCRIPTOR = {
    "columns": [
        {"name": "lead_id", "type": "string", "isJsonb": False},
        {"name": "latest_stage_observed", "type": "string", "isJsonb": False},
        {"name": "plan_name", "type": "string", "isJsonb": True},
    ],
    "jsonb_keys": ["plan_name"],
}


class ClinicalExplicitColumnsTests(unittest.IsolatedAsyncioTestCase):
    """clinical.dim_patient has explicit allowed_* columns; types still come
    from introspection. Patched so no live DB is needed."""

    async def test_real_columns_with_types_and_pii_flag_present(self) -> None:
        with patch(
            "app.services.orchestration_authoring.field_discovery."
            "introspect_static_schema_descriptor",
            return_value=_CLINICAL_DESCRIPTOR,
        ) as introspect:
            fields = await list_cohort_fields(
                db=object(),
                app_id="inside-sales",
                source_ref="clinical.dim_patient",
            )

        # Introspection was driven by the source's explicit allowed columns.
        _, kwargs = introspect.call_args
        self.assertEqual(
            kwargs["schema_qualified_table"], "clinical.dim_patient"
        )

        by_name = {f.name: f for f in fields}
        self.assertIn("hba1c_latest", by_name)
        self.assertIn("primary_condition", by_name)
        self.assertEqual(by_name["hba1c_latest"].type, "number")
        self.assertEqual(by_name["active"].type, "boolean")
        self.assertEqual(by_name["last_visit_at"].type, "datetime")

        # filterable mirrors allowed_filter_columns on the source.
        self.assertTrue(by_name["primary_condition"].filterable)
        self.assertFalse(by_name["first_name"].filterable)

        # Every field carries the pii flag. dim_patient is NOT a manifest
        # table, so every flag is present and False (documented in report).
        for f in fields:
            self.assertIsInstance(f, CohortFieldRef)
            self.assertIsInstance(f.pii, bool)
            self.assertFalse(f.pii)


class CrmIntrospectionBranchTests(unittest.IsolatedAsyncioTestCase):
    """crm.lead_record has EMPTY static allowed lists => the full column set
    comes from live introspection. Patched with a fake descriptor."""

    async def test_introspection_drives_columns(self) -> None:
        with patch(
            "app.services.orchestration_authoring.field_discovery."
            "introspect_static_schema_descriptor",
            return_value=_INTROSPECTED_DESCRIPTOR,
        ) as introspect:
            fields = await list_cohort_fields(
                db=object(),
                app_id="inside-sales",
                source_ref="crm.lead_record",
            )

        _, kwargs = introspect.call_args
        self.assertEqual(
            kwargs["schema_qualified_table"], "analytics.crm_lead_record"
        )
        # Empty allowed_columns => pass None so the live set can't drift.
        self.assertIsNone(kwargs.get("allowed_columns"))

        names = {f.name for f in fields}
        self.assertEqual(names, {"lead_id", "latest_stage_observed", "plan_name"})

        by_name = {f.name: f for f in fields}
        # Empty allowed_filter_columns => every introspected column filterable.
        self.assertTrue(by_name["lead_id"].filterable)
        # crm_lead_record is a hidden mirror, not a manifest table => no PII.
        for f in fields:
            self.assertFalse(f.pii)


class UnknownSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_source_ref_raises(self) -> None:
        from app.services.orchestration.source_catalog import SourceCatalogError

        with self.assertRaises(SourceCatalogError):
            await list_cohort_fields(
                db=object(),
                app_id="inside-sales",
                source_ref="nope.not_a_source",
            )


if __name__ == "__main__":
    unittest.main()
