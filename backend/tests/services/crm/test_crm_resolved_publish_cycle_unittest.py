"""3.3 (live DB) — the publish cycle: rebuild the matview, then the contract validates green.

Seeds a lead + slot + map, rebuilds the resolved surfaces, and runs ``validate_resolved_contract``
end to end: the built matview carries every projected fragment column AND a resolved-column exemplar
passes the SAME ``check_before`` + ``prepare_query`` Sherlock runs. This is the GATE-3 publish-cycle
evidence — boot validation is never asked to see the per-tenant matview.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.crm import CrmFieldMap, CrmLead, CrmLeadExt
from app.services.crm.crm_resolved_fragment import build_crm_fragment, validate_resolved_contract
from app.services.crm.crm_resolved_populator import rebuild_resolved_surfaces

pytestmark = pytest.mark.asyncio

_APP = "inside-sales"


async def test_publish_cycle_builds_and_validates(db_session, seed_tenant_user_app):
    tenant, _user, _seed_app = seed_tenant_user_app
    app = _APP
    conn = uuid.uuid4()

    lead = CrmLead(id=uuid.uuid4(), tenant_id=tenant, app_id=app, lead_id="p-700", lead_stage="Interested")
    db_session.add(lead)
    await db_session.flush()
    db_session.add(CrmLeadExt(id=uuid.uuid4(), crm_lead_id=lead.id, tenant_id=tenant, app_id=app, txt_01="Diabetes"))
    for slot, semantic in (("lead_id", "lead_id"), ("lead_stage", "lead_stage"), ("txt_01", "condition")):
        db_session.add(CrmFieldMap(
            id=uuid.uuid4(), tenant_id=tenant, app_id=app, connection_id=conn,
            record_type="lead", slot=slot, semantic_key=semantic, source_field="x", data_type="text",
        ))
    await db_session.flush()

    await rebuild_resolved_surfaces(db_session, tenant_id=tenant, app_id=app, connection_id=conn)

    # fragment projects the resolved columns
    fragment = await build_crm_fragment(db_session, tenant_id=tenant, app_id=app)
    assert fragment is not None
    lead_grain = next(g for g in fragment.grains if g.logical_table == "dim_lead")
    assert "condition" in {c.name for c in lead_grain.columns}

    # the contract validates: matview parity + the real enforcers accept resolved SQL
    validated = await validate_resolved_contract(db_session, tenant_id=tenant, app_id=app)
    assert validated is not None

    # sanity: the matview is queryable on the resolved name
    val = (await db_session.execute(text(
        f"SELECT condition FROM analytics.{lead_grain.matview_table} WHERE lead_id = 'p-700'"
    ))).scalar_one()
    assert val == "Diabetes"
