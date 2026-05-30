"""S0 prune guards — assert the dead Sherlock strata are gone for good.

Scope of this file (S0.1 + S0.2): the dead grounding package and the
ontology subsystem. Other S0 items add their own cases here later.
"""
import importlib

import pytest


def test_dead_sherlock_grounding_package_is_gone():
    for mod in (
        "app.services.sherlock",
        "app.services.sherlock.bundle",
        "app.services.sherlock.platform_ontology",
        "app.services.sherlock.scope_guard",
    ):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(mod)


def test_ontology_orm_is_gone():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.models.sherlock_ontology")
    import app.models as m

    for sym in ("SherlockOntologyClass", "SherlockOntologyEntityType", "SherlockEntityResolver"):
        assert not hasattr(m, sym), f"{sym} still exported from app.models"


@pytest.mark.parametrize("mod", [
    "app.services.chat_engine.prompt_generator",
    "app.services.chat_engine.tool_description_generator",
])
def test_dead_prompt_generators_are_gone(mod):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(mod)


def test_manifest_has_no_dead_surface_fields():
    from app.services.chat_engine.manifest import AppManifest
    fields = set(AppManifest.model_fields)
    assert "data_surfaces" not in fields
    assert "tool_vocabulary" not in fields
    import app.services.chat_engine.manifest as mani
    assert not hasattr(mani, "EXTERNAL_SURFACE_SOURCES")
    assert not hasattr(mani, "DataSurface")


def test_reason_code_registry_has_only_real_packs():
    import app.services.chat_engine.reason_codes as r
    # No concrete pack injects into the static registry today; the only
    # registered pack (orchestration.authoring) keeps its own frozenset and
    # never calls register_pack_reason_codes. So the lean end-state is empty.
    assert r.PACK_REASON_CODES == {}
    # The orphaned aggregate/sub-set frozensets are gone.
    for sym in (
        "ANALYTICS_REASON_CODES",
        "REPORT_BUILDER_REASON_CODES",
        "ANALYTICS_CHART_REASON_CODES",
        "ANALYTICS_SQL_REASON_CODES",
        "ANALYTICS_ENTITY_REASON_CODES",
        "REPORT_BUILDER_BLUEPRINT_REASON_CODES",
    ):
        assert not hasattr(r, sym), f"{sym} still present in reason_codes"
    # Symbols the live data_specialist path reads survive the prune.
    assert hasattr(r, "HARNESS_SHARED_REASON_CODES")
    assert r.CG_EMIT_FAILED == "CG_EMIT_FAILED"
