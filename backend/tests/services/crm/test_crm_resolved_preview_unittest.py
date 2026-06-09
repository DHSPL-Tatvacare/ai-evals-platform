"""3.5 (live DB) — the resolved-preview sample returns clean named columns + rows, hides scope.

Backs the editor's 'what Sherlock will see' panel: after a rebuild, ``resolved_sample`` returns the
resolved column names (``condition``, not ``txt_01``; no ``tenant_id``/``app_id``) and stringified
sample rows. Empty when no matview is built (no published map).
"""
from __future__ import annotations

import uuid

import pytest

from app.models.crm import CrmFieldMap, CrmLead, CrmLeadExt
from app.services.crm.crm_resolved_populator import rebuild_resolved_surfaces, resolved_sample

pytestmark = pytest.mark.asyncio

_APP = "inside-sales"


async def test_preview_empty_without_a_built_matview(db_session):
    # A tenant with no built matview returns empty — use a fresh tenant so no prior run's
    # matview (DDL isn't rolled back with the test transaction) leaks in.
    cols, rows = await resolved_sample(db_session, tenant_id=uuid.uuid4(), app_id=_APP, grain="lead")
    assert cols == [] and rows == []


async def test_preview_returns_resolved_columns_and_rows(db_session, seed_tenant_user_app):
    tenant, _u, _a = seed_tenant_user_app
    conn = uuid.uuid4()
    lead = CrmLead(id=uuid.uuid4(), tenant_id=tenant, app_id=_APP, lead_id="p-555", lead_stage="Converted")
    db_session.add(lead)
    await db_session.flush()
    db_session.add(CrmLeadExt(id=uuid.uuid4(), crm_lead_id=lead.id, tenant_id=tenant, app_id=_APP, txt_01="Diabetes"))
    for slot, semantic in (("lead_id", "lead_id"), ("lead_stage", "lead_stage"), ("txt_01", "condition")):
        db_session.add(CrmFieldMap(
            id=uuid.uuid4(), tenant_id=tenant, app_id=_APP, connection_id=conn,
            record_type="lead", slot=slot, semantic_key=semantic, source_field="x", data_type="text",
        ))
    await db_session.flush()
    await rebuild_resolved_surfaces(db_session, tenant_id=tenant, app_id=_APP, connection_id=conn)

    cols, rows = await resolved_sample(db_session, tenant_id=tenant, app_id=_APP, grain="lead")
    assert "condition" in cols and "lead_stage" in cols
    assert "tenant_id" not in cols and "app_id" not in cols       # scope hidden
    assert not any(c.startswith("txt_") for c in cols)            # no raw slot
    row = next(r for r in rows if r["lead_id"] == "p-555")
    assert row["condition"] == "Diabetes" and row["lead_stage"] == "Converted"
