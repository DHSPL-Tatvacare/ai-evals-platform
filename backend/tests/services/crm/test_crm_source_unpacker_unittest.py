"""The ONE CRM unpacker — landed raw + field-map → core + slots, provider-agnostically.

DB-backed against the live docker Postgres (``db_session`` rolls back). The unpacker is
the only writer of CRM-derived rows; adapters never reach here. Behaviour comes entirely
from ``crm_field_map`` — no provider branch.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.models.crm import (
    CrmActivity,
    CrmFieldMap,
    CrmLead,
    CrmLeadExt,
    CrmSourceRecord,
)
from app.services.crm.crm_source_unpacker import unpack

pytestmark = pytest.mark.asyncio

LSQ_LEAD = {
    "ProspectID": "a1b2c3",
    "FirstName": "Asha",
    "Phone": "9876543210",
    "ProspectStage": "Interested",
    "mx_utm_disease": "Diabetes",
    "mx_City": "Pune",
}
LSQ_ACTIVITY = {
    "ProspectActivityId": "act-991",
    "RelatedProspectId": "a1b2c3",
    "ActivityEvent": 22,
    "Status": "Answered",
    "mx_Custom_3": "182",
}


async def _land(db, *, tenant, app, conn, source_object, record_type, sid, raw):
    db.add(
        CrmSourceRecord(
            id=uuid.uuid4(), tenant_id=tenant, app_id=app, connection_id=conn,
            source_object=source_object, record_type=record_type,
            source_record_id=sid, raw_payload=raw,
        )
    )
    await db.flush()


async def _bind(db, *, tenant, app, conn, record_type, rows):
    for slot, semantic, source_field, data_type, value_map in rows:
        db.add(
            CrmFieldMap(
                id=uuid.uuid4(), tenant_id=tenant, app_id=app, connection_id=conn,
                record_type=record_type, slot=slot, semantic_key=semantic,
                source_field=source_field, data_type=data_type, value_map=value_map,
            )
        )
    await db.flush()


_LEAD_BINDINGS = [
    ("lead_id", "lead_id", "ProspectID", "text", None),
    ("first_name", "first_name", "FirstName", "text", None),
    ("phone_number", "phone", "Phone", "text", None),
    ("lead_stage", "lead_stage", "ProspectStage", "text", {"Interested": "interested"}),
    ("txt_01", "condition", "mx_utm_disease", "text", None),
]


async def test_unpack_writes_core_slots_value_map_and_phone_norm(db_session, seed_tenant_user_app):
    tenant, _user, app = seed_tenant_user_app
    conn = uuid.uuid4()
    await _land(db_session, tenant=tenant, app=app, conn=conn,
                source_object="Lead", record_type="lead", sid="a1b2c3", raw=LSQ_LEAD)
    await _bind(db_session, tenant=tenant, app=app, conn=conn, record_type="lead", rows=_LEAD_BINDINGS)

    result = await unpack(db_session, tenant_id=tenant, app_id=app, connection_id=conn, source_system="lsq")

    lead = (await db_session.execute(
        select(CrmLead).where(CrmLead.tenant_id == tenant, CrmLead.app_id == app, CrmLead.lead_id == "a1b2c3")
    )).scalar_one()
    assert lead.first_name == "Asha"
    assert lead.phone_number == "9876543210"
    assert lead.phone_number_norm == "+919876543210"
    assert lead.lead_stage == "interested"  # value_map translated
    ext = (await db_session.execute(
        select(CrmLeadExt).where(CrmLeadExt.crm_lead_id == lead.id)
    )).scalar_one()
    assert ext.txt_01 == "Diabetes"
    assert result.upserted == 1


async def test_unpack_is_idempotent(db_session, seed_tenant_user_app):
    tenant, _user, app = seed_tenant_user_app
    conn = uuid.uuid4()
    await _land(db_session, tenant=tenant, app=app, conn=conn,
                source_object="Lead", record_type="lead", sid="a1b2c3", raw=LSQ_LEAD)
    await _bind(db_session, tenant=tenant, app=app, conn=conn, record_type="lead", rows=_LEAD_BINDINGS)

    await unpack(db_session, tenant_id=tenant, app_id=app, connection_id=conn, source_system="lsq")
    await unpack(db_session, tenant_id=tenant, app_id=app, connection_id=conn, source_system="lsq")

    count = (await db_session.execute(
        select(func.count()).select_from(CrmLead).where(CrmLead.tenant_id == tenant, CrmLead.app_id == app)
    )).scalar_one()
    assert count == 1


async def test_unpack_replays_from_raw_after_mapping_edit(db_session, seed_tenant_user_app):
    tenant, _user, app = seed_tenant_user_app
    conn = uuid.uuid4()
    await _land(db_session, tenant=tenant, app=app, conn=conn,
                source_object="Lead", record_type="lead", sid="a1b2c3", raw=LSQ_LEAD)
    await _bind(db_session, tenant=tenant, app=app, conn=conn, record_type="lead", rows=_LEAD_BINDINGS)
    await unpack(db_session, tenant_id=tenant, app_id=app, connection_id=conn, source_system="lsq")

    # edit: repoint the condition slot at a different source field — no re-sync
    binding = (await db_session.execute(
        select(CrmFieldMap).where(CrmFieldMap.connection_id == conn, CrmFieldMap.slot == "txt_01")
    )).scalar_one()
    binding.source_field = "mx_City"
    await db_session.flush()
    await unpack(db_session, tenant_id=tenant, app_id=app, connection_id=conn, source_system="lsq")

    lead = (await db_session.execute(
        select(CrmLead).where(CrmLead.lead_id == "a1b2c3", CrmLead.tenant_id == tenant)
    )).scalar_one()
    ext = (await db_session.execute(select(CrmLeadExt).where(CrmLeadExt.crm_lead_id == lead.id))).scalar_one()
    assert ext.txt_01 == "Pune"


async def test_activity_unpacks_with_lead_link(db_session, seed_tenant_user_app):
    tenant, _user, app = seed_tenant_user_app
    conn = uuid.uuid4()
    await _land(db_session, tenant=tenant, app=app, conn=conn,
                source_object="Activity", record_type="activity", sid="act-991", raw=LSQ_ACTIVITY)
    await _bind(db_session, tenant=tenant, app=app, conn=conn, record_type="activity", rows=[
        ("source_activity_id", "source_activity_id", "ProspectActivityId", "text", None),
        ("lead_id", "lead_id", "RelatedProspectId", "text", None),
        ("status", "status", "Status", "text", None),
        ("duration_seconds", "duration_seconds", "mx_Custom_3", "int", None),
    ])

    result = await unpack(db_session, tenant_id=tenant, app_id=app, connection_id=conn, source_system="lsq")

    act = (await db_session.execute(
        select(CrmActivity).where(CrmActivity.source_activity_id == "act-991", CrmActivity.tenant_id == tenant)
    )).scalar_one()
    assert act.lead_id == "a1b2c3"
    assert act.duration_seconds == 182
    assert result.upserted == 1


async def test_activity_without_lead_link_is_skipped(db_session, seed_tenant_user_app):
    tenant, _user, app = seed_tenant_user_app
    conn = uuid.uuid4()
    await _land(db_session, tenant=tenant, app=app, conn=conn,
                source_object="Activity", record_type="activity", sid="act-991", raw=LSQ_ACTIVITY)
    # no lead_id binding → cannot resolve a lead → orphan-guard skips it
    await _bind(db_session, tenant=tenant, app=app, conn=conn, record_type="activity", rows=[
        ("source_activity_id", "source_activity_id", "ProspectActivityId", "text", None),
        ("status", "status", "Status", "text", None),
    ])

    result = await unpack(db_session, tenant_id=tenant, app_id=app, connection_id=conn, source_system="lsq")

    count = (await db_session.execute(
        select(func.count()).select_from(CrmActivity).where(CrmActivity.tenant_id == tenant)
    )).scalar_one()
    assert count == 0
    assert result.skipped >= 1
