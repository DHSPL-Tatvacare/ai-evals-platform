"""3.1 filter (live DB) — an active definition's filter narrows the rebuilt resolved matview.

Lands two leads (one matching the filter, one not) + a field map + an active SourceDatasetDefinition
whose filter_predicate selects only the matching stage, rebuilds, then proves the matview exposes the
matching lead and excludes the non-matching one — "Activate alone makes the data match the filter",
no re-sync. Runs inside the rolled-back test transaction (DDL is transactional in Postgres).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.models.crm import CrmFieldMap, CrmLead, CrmLeadExt, SourceDatasetDefinition
from app.services.crm.crm_resolved_populator import (
    rebuild_resolved_surfaces,
    resolved_matview_name,
)

pytestmark = pytest.mark.asyncio


async def test_active_filter_excludes_nonmatching_rows(db_session, seed_tenant_user_app):
    tenant, _user, app = seed_tenant_user_app
    conn = uuid.uuid4()

    for lead_id, stage, cond in (("won-1", "won", "Diabetes"), ("new-1", "New", "Hypertension")):
        lead = CrmLead(
            id=uuid.uuid4(), tenant_id=tenant, app_id=app, lead_id=lead_id,
            lead_stage=stage, phone_number="9000000000",
        )
        db_session.add(lead)
        await db_session.flush()
        db_session.add(CrmLeadExt(
            id=uuid.uuid4(), crm_lead_id=lead.id, tenant_id=tenant, app_id=app, txt_01=cond
        ))

    for slot, semantic in (("lead_id", "lead_id"), ("lead_stage", "lead_stage"), ("txt_01", "condition")):
        db_session.add(CrmFieldMap(
            id=uuid.uuid4(), tenant_id=tenant, app_id=app, connection_id=conn,
            record_type="lead", slot=slot, semantic_key=semantic, source_field="x", data_type="text",
        ))

    now = datetime.now(timezone.utc)
    db_session.add(SourceDatasetDefinition(
        id=uuid.uuid4(), tenant_id=tenant, app_id=app, connection_id=conn, record_type="lead",
        filter_predicate={"field": "lead_stage", "op": "in", "value": ["won"]},
        status="active", version=1, created_at=now, updated_at=now,
    ))
    await db_session.flush()

    rebuilt = await rebuild_resolved_surfaces(db_session, tenant_id=tenant, app_id=app, connection_id=conn)
    assert "lead" in rebuilt

    mv = resolved_matview_name("lead", tenant, app)
    ids = {
        r[0] for r in (await db_session.execute(
            text(f"SELECT lead_id FROM analytics.{mv}")
        )).all()
    }
    assert "won-1" in ids        # matches the active filter
    assert "new-1" not in ids    # filtered out at the resolved surface, no re-sync needed
