"""Every ProviderSpec self-classifies via ``kind`` (capability category).

``kind`` lets a provider declare whether it is a ``crm_source`` vs a
``messaging`` / ``voice`` dispatch provider, WITHOUT requiring a registered
adapter (lsq/msg91/webhook have no adapter, so ``capability_for_vendor`` is
None for them). The CRM mapping surface filters connections on ``kind ==
'crm_source'``.
"""
from __future__ import annotations

import pytest

from app.services.orchestration.connections.provider_specs import (
    PROVIDER_SPECS,
    to_json_schema,
)

_ALLOWED_KINDS = {"messaging", "voice", "crm_source"}

_EXPECTED_KIND = {
    "bolna": "voice",
    "wati": "messaging",
    "aisensy": "messaging",
    "lsq": "crm_source",
    "msg91": "messaging",
    "webhook": "messaging",
}


@pytest.mark.parametrize("provider", sorted(PROVIDER_SPECS.keys()))
def test_every_spec_has_a_valid_kind(provider: str):
    spec = PROVIDER_SPECS[provider]
    assert spec.kind in _ALLOWED_KINDS, (
        f"{provider}: kind {spec.kind!r} not in {_ALLOWED_KINDS}"
    )


@pytest.mark.parametrize("provider,expected", sorted(_EXPECTED_KIND.items()))
def test_kind_matches_expected_category(provider: str, expected: str):
    assert PROVIDER_SPECS[provider].kind == expected


def test_lsq_is_crm_source():
    assert PROVIDER_SPECS["lsq"].kind == "crm_source"


@pytest.mark.parametrize("provider", sorted(PROVIDER_SPECS.keys()))
def test_json_schema_emits_kind(provider: str):
    schema = to_json_schema(provider)
    assert schema.get("x-kind") == PROVIDER_SPECS[provider].kind


def test_provider_schema_response_carries_kind():
    from app.schemas.orchestration_connection import ProviderSpecResponse
    from app.services.orchestration.api.connections import get_provider_schema

    payload = get_provider_schema("lsq")
    assert payload["kind"] == "crm_source"
    # The response model must accept (and expose) the new field.
    resp = ProviderSpecResponse(**payload)
    assert resp.kind == "crm_source"
