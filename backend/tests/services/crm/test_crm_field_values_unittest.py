"""Observed values for a source field (drives exhaustive value-map coverage in the editor)."""
from __future__ import annotations

import uuid

import pytest

from app.models.crm import CrmSourceRecord
from app.services.crm.field_values import distinct_field_values

pytestmark = pytest.mark.asyncio


async def _land(db, *, tenant, app, conn, sid, raw):
    db.add(CrmSourceRecord(
        id=uuid.uuid4(), tenant_id=tenant, app_id=app, connection_id=conn,
        source_object="Lead", record_type="lead", source_record_id=sid, raw_payload=raw,
    ))


async def test_distinct_values_from_landed_raw(db_session, seed_tenant_user_app):
    tenant, _user, app = seed_tenant_user_app
    conn = uuid.uuid4()
    await _land(db_session, tenant=tenant, app=app, conn=conn, sid="1", raw={"ProspectStage": "New"})
    await _land(db_session, tenant=tenant, app=app, conn=conn, sid="2", raw={"ProspectStage": "New"})
    await _land(db_session, tenant=tenant, app=app, conn=conn, sid="3", raw={"ProspectStage": "Interested"})
    await db_session.flush()

    values = await distinct_field_values(
        db_session, tenant_id=tenant, app_id=app, connection_id=conn,
        record_type="lead", field="ProspectStage",
    )
    assert set(values) == {"New", "Interested"}
