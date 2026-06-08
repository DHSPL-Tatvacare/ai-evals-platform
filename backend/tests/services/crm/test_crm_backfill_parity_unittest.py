"""Backfill parity — the new map-driven path reproduces the legacy serving fields.

Anchored to the real legacy normaliser (``lsq_client.normalize_lead``), not a hand-copied
expectation: we land an LSQ raw record, apply the field map that mirrors the legacy lead
mapping, unpack, and assert the resulting ``crm_lead`` matches ``normalize_lead`` field for
field. No live LSQ call. (Known, accepted divergence: the legacy path collapses incidental
whitespace on a few labels via ``_clean_label``; the generic unpacker lands values verbatim,
so dirty-whitespace rows differ — value normalisation is expressed in the map, not in code.)
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.crm import CrmFieldMap, CrmLead, CrmLeadExt, CrmSourceRecord
from app.services.crm.crm_source_unpacker import unpack
from app.services.lsq_client import normalize_lead

pytestmark = pytest.mark.asyncio

# A clean LSQ lead (no stray whitespace) — every legacy-cleaned field is already canonical.
RAW = {
    "ProspectID": "p-100",
    "FirstName": "Asha",
    "LastName": "Rao",
    "Phone": "9876543210",
    "EmailAddress": "asha@example.com",
    "ProspectStage": "Interested",
    "OwnerIdName": "Rep One",
    "Source": "Facebook",
    "CreatedOn": "2025-01-15 10:30:00",
    "mx_utm_disease": "Diabetes",
}

# The field map that mirrors the legacy LSQ → dim_lead lead mapping.
MIRROR_MAP = [
    ("lead_id", "lead_id", "ProspectID", "text"),
    ("first_name", "first_name", "FirstName", "text"),
    ("last_name", "last_name", "LastName", "text"),
    ("phone_number", "phone", "Phone", "text"),
    ("email", "email", "EmailAddress", "text"),
    ("lead_stage", "lead_stage", "ProspectStage", "text"),
    ("owner_name", "owner_name", "OwnerIdName", "text"),
    ("source", "source", "Source", "text"),
    ("created_at", "created_at", "CreatedOn", "datetime"),
    ("txt_01", "condition", "mx_utm_disease", "text"),
]


async def test_unpack_reproduces_legacy_normalised_lead_field_for_field(db_session, seed_tenant_user_app):
    tenant, _user, app = seed_tenant_user_app
    conn = uuid.uuid4()
    db_session.add(CrmSourceRecord(
        id=uuid.uuid4(), tenant_id=tenant, app_id=app, connection_id=conn,
        source_object="Lead", record_type="lead", source_record_id="p-100", raw_payload=RAW,
    ))
    for slot, semantic, source_field, data_type in MIRROR_MAP:
        db_session.add(CrmFieldMap(
            id=uuid.uuid4(), tenant_id=tenant, app_id=app, connection_id=conn,
            record_type="lead", slot=slot, semantic_key=semantic,
            source_field=source_field, data_type=data_type, value_map=None,
        ))
    await db_session.flush()

    await unpack(db_session, tenant_id=tenant, app_id=app, connection_id=conn, source_system="lsq")

    legacy = normalize_lead(RAW)
    lead = (await db_session.execute(
        select(CrmLead).where(CrmLead.tenant_id == tenant, CrmLead.lead_id == "p-100")
    )).scalar_one()
    ext = (await db_session.execute(
        select(CrmLeadExt).where(CrmLeadExt.crm_lead_id == lead.id)
    )).scalar_one()

    # field-for-field against the legacy normaliser
    assert lead.lead_id == legacy["prospectId"]
    assert lead.first_name == legacy["firstName"]
    assert lead.last_name == legacy["lastName"]
    assert lead.phone_number == legacy["phone"]
    assert lead.email == legacy["email"]
    assert lead.lead_stage == legacy["prospectStage"]
    assert lead.owner_name == legacy["agentName"]
    assert lead.source == legacy["source"]
    assert lead.created_at.strftime("%Y-%m-%d %H:%M:%S") == legacy["createdOn"]
    assert ext.txt_01 == legacy["condition"]
