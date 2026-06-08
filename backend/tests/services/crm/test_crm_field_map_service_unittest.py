"""Field-map publish service — closed-list validation, lead-link guard, versioned replace."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.models.crm import CrmFieldMap
from app.services.crm.field_map_service import BindingInput, publish_field_map

pytestmark = pytest.mark.asyncio


def _b(slot, semantic, source_field, data_type="text", value_map=None):
    return BindingInput(slot=slot, semantic_key=semantic, source_field=source_field,
                        data_type=data_type, value_map=value_map)


async def test_publish_persists_and_bumps_version(db_session, seed_tenant_user_app):
    tenant, _user, app = seed_tenant_user_app
    conn = uuid.uuid4()
    bindings = [_b("lead_id", "lead_id", "ProspectID"), _b("phone_number", "phone", "Phone")]

    v1 = await publish_field_map(db_session, tenant_id=tenant, app_id=app, connection_id=conn,
                                 record_type="lead", bindings=bindings)
    assert v1 == 1
    v2 = await publish_field_map(db_session, tenant_id=tenant, app_id=app, connection_id=conn,
                                 record_type="lead", bindings=bindings)
    assert v2 == 2

    rows = (await db_session.execute(
        select(CrmFieldMap).where(CrmFieldMap.connection_id == conn, CrmFieldMap.record_type == "lead")
    )).scalars().all()
    assert len(rows) == 2  # replaced, not appended
    assert all(r.version == 2 for r in rows)


async def test_publish_rejects_target_outside_closed_list(db_session, seed_tenant_user_app):
    tenant, _user, app = seed_tenant_user_app
    conn = uuid.uuid4()
    with pytest.raises(ValueError):
        await publish_field_map(db_session, tenant_id=tenant, app_id=app, connection_id=conn,
                                record_type="lead", bindings=[_b("not_a_real_column", "x", "Foo")])


async def test_publish_activity_requires_lead_link(db_session, seed_tenant_user_app):
    tenant, _user, app = seed_tenant_user_app
    conn = uuid.uuid4()
    # no lead_id binding → the join anchor is missing → reject
    with pytest.raises(ValueError):
        await publish_field_map(db_session, tenant_id=tenant, app_id=app, connection_id=conn,
                                record_type="activity",
                                bindings=[_b("source_activity_id", "source_activity_id", "ProspectActivityId")])

    # with the lead-link it publishes
    v = await publish_field_map(db_session, tenant_id=tenant, app_id=app, connection_id=conn,
                                record_type="activity", bindings=[
                                    _b("source_activity_id", "source_activity_id", "ProspectActivityId"),
                                    _b("lead_id", "lead_id", "RelatedProspectId"),
                                ])
    assert v == 1
    count = (await db_session.execute(
        select(func.count()).select_from(CrmFieldMap).where(CrmFieldMap.connection_id == conn)
    )).scalar_one()
    assert count == 2
