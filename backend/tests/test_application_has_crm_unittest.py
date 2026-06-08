"""App.config `hasCrm` flag — which apps surface the CRM ingestion experience.

The mapping itself lives in ``crm_field_map``, never in App.config; this flag only
gates whether the CRM surface is shown for the app.
"""
from __future__ import annotations

from app.models.application import Application


def test_has_crm_true_when_flag_set():
    app = Application(slug="inside-sales", display_name="Inside Sales", config={"hasCrm": True})
    assert app.has_crm is True


def test_has_crm_false_when_flag_absent():
    app = Application(slug="voice-rx", display_name="Voice Rx", config={})
    assert app.has_crm is False


def test_has_crm_false_when_config_none():
    app = Application(slug="x", display_name="X", config=None)
    assert app.has_crm is False
