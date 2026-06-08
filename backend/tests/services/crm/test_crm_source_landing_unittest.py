"""Landing layer — adapter drafts → ``crm_source_record`` (idempotent UPSERT, the replay tape)."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.models.crm import CrmSourceRecord
from app.services.crm.adapters.protocol import SourceRecordDraft
from app.services.crm.crm_source_sync import land_records

pytestmark = pytest.mark.asyncio


async def test_land_inserts_then_upserts_in_place(db_session, seed_tenant_user_app):
    tenant, _user, app = seed_tenant_user_app
    conn = uuid.uuid4()
    draft_v1 = SourceRecordDraft("Lead", "lead", "a1b2c3", {"ProspectID": "a1b2c3", "ProspectStage": "New"})

    landed = await land_records(db_session, tenant_id=tenant, app_id=app, connection_id=conn, drafts=[draft_v1])
    assert landed == 1

    row = (await db_session.execute(
        select(CrmSourceRecord).where(
            CrmSourceRecord.tenant_id == tenant, CrmSourceRecord.connection_id == conn,
            CrmSourceRecord.source_record_id == "a1b2c3",
        )
    )).scalar_one()
    assert row.raw_payload["ProspectStage"] == "New"
    assert row.source_record_hash
    first_synced = row.first_synced_at
    assert first_synced is not None

    # same natural key, changed payload → updates in place, no new row, first_synced preserved
    draft_v2 = SourceRecordDraft("Lead", "lead", "a1b2c3", {"ProspectID": "a1b2c3", "ProspectStage": "Interested"})
    await land_records(db_session, tenant_id=tenant, app_id=app, connection_id=conn, drafts=[draft_v2])

    count = (await db_session.execute(
        select(func.count()).select_from(CrmSourceRecord).where(CrmSourceRecord.connection_id == conn)
    )).scalar_one()
    assert count == 1
    db_session.expire_all()  # the Core UPSERT bypasses the identity map; read real DB state
    refreshed = (await db_session.execute(
        select(CrmSourceRecord).where(CrmSourceRecord.connection_id == conn)
    )).scalar_one()
    assert refreshed.raw_payload["ProspectStage"] == "Interested"
    assert refreshed.first_synced_at == first_synced
