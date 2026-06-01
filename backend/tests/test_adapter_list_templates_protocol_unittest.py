"""Uniform read-only list_templates on the MessagingAdapter Protocol + authoring read-only safety boundary.

No live WATI. The WATI getMessageTemplates GET is exercised via httpx.MockTransport
against a verbatim response shape; the AiSensy path stays unsupported.
"""
from __future__ import annotations

import httpx
import pytest

from app.services.orchestration.adapters import wati as wati_mod
from app.services.orchestration.adapters.protocol import MessagingAdapter
from app.services.orchestration.adapters.wati import WatiAdapter


_WATI_CONNECTION = {
    "base_url": "https://live-mt-server.wati.io",
    "wati_tenant_id": "123456",
    "api_token": "tok",
}

# Verbatim getMessageTemplates response shape (messageTemplates envelope).
_WATI_GET_MESSAGE_TEMPLATES = {
    "messageTemplates": [
        {
            "elementName": "document_approved_latest",
            "templateLanguage": "en",
            "status": "APPROVED",
            "customParams": [
                {"paramName": "name", "paramValue": "John"},
                {"paramName": "documentType", "paramValue": "Prescription"},
            ],
            "body": "Hi *{{1}}*,\nyour *{{2}}* has been approved.",
        },
        {
            "elementName": "wc_gf_aiagent",
            "templateLanguage": "en",
            "status": "APPROVED",
            "customParams": [],
            "body": "Hi {patient name}",
        },
    ]
}


def _patch_transport(monkeypatch):
    transport = httpx.MockTransport(
        lambda r: httpx.Response(200, json=_WATI_GET_MESSAGE_TEMPLATES),
    )
    monkeypatch.setattr(
        "app.services.orchestration.adapters.wati._make_client",
        lambda timeout=30.0: httpx.AsyncClient(transport=transport, timeout=timeout),
    )


@pytest.mark.asyncio
async def test_wati_list_templates_matches_list_message_templates(monkeypatch):
    _patch_transport(monkeypatch)
    adapter = WatiAdapter()
    via_alias = await adapter.list_templates(_WATI_CONNECTION)
    _patch_transport(monkeypatch)
    via_original = await adapter.list_message_templates(_WATI_CONNECTION)
    assert via_alias == via_original
    assert [t["name"] for t in via_alias] == ["document_approved_latest", "wc_gf_aiagent"]


def test_protocol_declares_list_templates():
    assert "list_templates" in MessagingAdapter.__dict__


def test_authoring_readonly_allowset_excludes_write_methods():
    from app.services.orchestration.adapters import AUTHORING_READONLY_ADAPTER_METHODS

    for write_method in (
        "send_template",
        "handle_webhook",
        "cancel_dispatch",
        "cancel_run_actions",
    ):
        assert write_method not in AUTHORING_READONLY_ADAPTER_METHODS

    assert "list_templates" in AUTHORING_READONLY_ADAPTER_METHODS
