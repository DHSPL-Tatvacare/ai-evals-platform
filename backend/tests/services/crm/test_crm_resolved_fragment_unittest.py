"""3.2 + 3.3 — the per-tenant fragment composes onto the static catalog and the real enforcers
accept resolved-column SQL against the matview.

This is the crux of the contained engine touch: a turn-time overlay swaps the lead surface's
physical table to the per-tenant matview and exposes the resolved columns, and a resolved-column
exemplar passes the SAME ``check_before`` + ``prepare_query`` the boot validator runs — so Sherlock
can generate SQL over ``condition`` / ``lead_stage`` against ``analytics.dim_lead__<slug>`` without
ever touching ``txt_NN`` / ``raw_payload``. No DB, no boot mutation: the static catalog is untouched.
"""
from __future__ import annotations

import uuid

from app.services.chat_engine.manifest_validator import validate_exemplars_through_enforcers
from app.services.chat_engine.workbench_catalog import load_workbench_catalog_strict
from app.services.crm.crm_resolved_fragment import (
    CrmResolvedFragment,
    FragmentColumn,
    FragmentGrain,
    compose_catalog,
)
from app.services.crm.crm_resolved_populator import resolved_matview_name

_TENANT = uuid.UUID("11111111-1111-1111-1111-111111111111")
_APP = "inside-sales"


def _fragment() -> CrmResolvedFragment:
    mv = resolved_matview_name("lead", _TENANT, _APP)
    cols = (
        FragmentColumn("lead_id", "nominal"),
        FragmentColumn("lead_stage", "nominal"),
        FragmentColumn("condition", "nominal", is_enum=True, sample_values=("Diabetes", "PCOS")),
    )
    sql = (
        f"SELECT lead_id, lead_stage, condition FROM analytics.{mv} "
        "WHERE tenant_id = :tenant_id AND app_id = :app_id LIMIT 50"
    )
    return CrmResolvedFragment(
        app_id=_APP, version=1,
        grains=(FragmentGrain("dim_lead", mv, "lead_id", cols),),
        exemplars=(("resolved_lead_sample", sql),),
    )


def test_compose_swaps_base_table_and_exposes_resolved_columns():
    catalog = load_workbench_catalog_strict(_APP)
    composed = compose_catalog(catalog, _fragment())

    mv = resolved_matview_name("lead", _TENANT, _APP)
    # the lead surface is rekeyed to the matview (so the bouncer accepts the physical name written)
    assert "dim_lead" not in composed.tables
    lead = composed.tables[mv]
    assert lead.name == mv and lead.qualified_table == f"analytics.{mv}"
    names = {c.name for c in lead.all_logical_columns()}
    assert {"lead_id", "lead_stage", "condition"} <= names
    assert not any(n.startswith("txt_") for n in names)
    # relationships that referenced dim_lead are rewritten to the matview key
    assert any(r.right_table == mv for r in composed.relationships)
    assert not any(r.right_table == "dim_lead" or r.left_table == "dim_lead" for r in composed.relationships)
    # the stale legacy-named exemplar (analytics.dim_lead / latest_stage_observed) is dropped
    assert not any(vq.name == "leads_stuck_over_7_days" for vq in composed.verified_queries)
    assert any(vq.name == "resolved_lead_sample" for vq in composed.verified_queries)
    # static catalog is never mutated
    assert catalog.tables["dim_lead"].qualified_table == "analytics.dim_lead"


def test_resolved_exemplar_passes_the_real_enforcers():
    catalog = load_workbench_catalog_strict(_APP)
    composed = compose_catalog(catalog, _fragment())
    rejections = validate_exemplars_through_enforcers(composed, _APP, raise_on_reject=False)
    assert not any(name == "resolved_lead_sample" for name, _ in rejections), rejections
