"""Boot-parse guard: every app manifest YAML parses against AppManifest.

AppManifest is ``extra="forbid"``; an orphaned ``data_surfaces:`` block left
in a YAML after the S0.4 field removal would fail parse here, before boot.
"""
import pytest

from app.services.chat_engine.manifest import MANIFESTS_DIR, load_manifest_from_path

APP_MANIFESTS = ["kaira-bot", "voice-rx", "inside-sales"]


@pytest.mark.parametrize("app_id", APP_MANIFESTS)
def test_app_manifest_parses(app_id):
    manifest = load_manifest_from_path(MANIFESTS_DIR / f"{app_id}.yaml")
    assert manifest.app_id == app_id


@pytest.mark.parametrize("app_id", APP_MANIFESTS)
def test_app_manifest_carries_no_dead_surface_keys(app_id):
    raw = (MANIFESTS_DIR / f"{app_id}.yaml").read_text()
    assert "data_surfaces:" not in raw
    assert "tool_vocabulary:" not in raw
