"""3.1 (live DB) — rebuilding the resolved surfaces produces a flat, named, slot-resolved matview.

Seeds one lead + its ext slots + a field map, rebuilds, then proves the materialized view exposes
the semantic column ``condition`` carrying the slot value and NEVER exposes ``txt_01`` / a slot —
the exact surface Sherlock reads. Runs inside the rolled-back test transaction (DDL is
transactional in Postgres, so the per-tenant matview never leaks).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.crm import CrmFieldMap, CrmLead, CrmLeadExt
from app.services.crm.crm_resolved_populator import (
    rebuild_resolved_surfaces,
    resolved_matview_name,
)

pytestmark = pytest.mark.asyncio


async def test_rebuild_exposes_resolved_columns_and_hides_slots(db_session, seed_tenant_user_app):
    tenant, _user, app = seed_tenant_user_app
    conn = uuid.uuid4()

    lead = CrmLead(
        id=uuid.uuid4(), tenant_id=tenant, app_id=app, lead_id="p-900",
        lead_stage="Interested", phone_number="9876543210",
    )
    db_session.add(lead)
    await db_session.flush()
    db_session.add(CrmLeadExt(id=uuid.uuid4(), crm_lead_id=lead.id, tenant_id=tenant, app_id=app, txt_01="Diabetes"))
    for slot, semantic in (("lead_id", "lead_id"), ("lead_stage", "lead_stage"), ("txt_01", "condition")):
        db_session.add(CrmFieldMap(
            id=uuid.uuid4(), tenant_id=tenant, app_id=app, connection_id=conn,
            record_type="lead", slot=slot, semantic_key=semantic, source_field="x", data_type="text",
        ))
    await db_session.flush()

    rebuilt = await rebuild_resolved_surfaces(db_session, tenant_id=tenant, app_id=app, connection_id=conn)
    assert "lead" in rebuilt

    mv = resolved_matview_name("lead", tenant, app)
    cols = {
        r[0] for r in (await db_session.execute(text(
            "SELECT a.attname FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'analytics' AND c.relname = :n AND c.relkind = 'm' AND a.attnum > 0"
        ), {"n": mv})).all()
    }
    assert "condition" in cols                       # slot resolved to its semantic name
    assert "lead_stage" in cols and "lead_id" in cols  # standard tier present
    assert not any(c.startswith("txt_") for c in cols)  # no raw slot ever surfaces

    row = (await db_session.execute(text(
        f"SELECT lead_id, lead_stage, condition FROM analytics.{mv} WHERE lead_id = 'p-900'"
    ))).one()
    assert row.lead_id == "p-900"
    assert row.lead_stage == "Interested"
    assert row.condition == "Diabetes"
