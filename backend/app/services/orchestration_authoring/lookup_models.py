"""Pydantic response models for the authoring pack's `list_*` lookup tools.

Per Decision §R5, these models **explicitly exclude** every credential
field name. ORM rows are NEVER serialized directly; the lookup handler
copies only the fields named here. Adding a new field here is the only
way credential data could leak — review accordingly.

The egress filter in `orchestration_authoring_pack.build_outcome` is the
second line of defense: it walks the serialized payload and rejects any
field whose name is in `CREDENTIAL_FIELD_BLOCKLIST` (Decision §R5).
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# Decision §R5. Field names rejected by the egress walker.
# Add a name here BEFORE writing a new lookup that touches a table
# with that column — the filter is otherwise the last line of defense.
CREDENTIAL_FIELD_BLOCKLIST: frozenset[str] = frozenset({
    'api_key',
    'apikey',
    'secret',
    'access_token',
    'config_encrypted',
    'password',
    'bearer',
    'webhook_token',
    'bolna_api_key',
    'wati_api_key',
    'private_key',
    'client_secret',
    'auth_token',
    'session_token',
})


class ProviderConnectionRef(BaseModel):
    """Tight reference shape for `list_provider_connections`.

    Drops the encrypted blob, the webhook token, and every credential-
    bearing field. The LLM only ever sees `(id, name, provider)`.
    """

    model_config = ConfigDict(extra='forbid')

    id: str
    name: str
    provider: str


class ActionTemplateRef(BaseModel):
    """Tight reference shape for `list_action_templates`."""

    model_config = ConfigDict(extra='forbid')

    id: str
    slug: str
    name: str
    channel: str


class WatiTemplateRef(BaseModel):
    """Tight reference shape for `list_wati_templates`.

    Each row is a normalized WATI message-template summary returned by
    the existing `list_connection_wati_templates` cache. Strings only.
    """

    model_config = ConfigDict(extra='forbid')

    name: str
    language: str
    status: str
    parameters: list[str] = Field(default_factory=list)


class CohortDatasetRef(BaseModel):
    """Tight reference shape for `list_cohort_datasets`."""

    model_config = ConfigDict(extra='forbid')

    id: str
    name: str
    latest_version_id: str | None = None


class NodeTypeRef(BaseModel):
    """One row in the `list_node_types` response.

    The LLM reads this to discover what nodes are available; `category`
    is a neutral palette grouping (ingress/dispatch/...).
    """

    model_config = ConfigDict(extra='forbid')

    node_type: str
    category: str
    workflow_types: list[str] = Field(default_factory=list)
    output_edges: list[str] = Field(default_factory=list)


# ----- response envelopes -----


class ProviderConnectionsList(BaseModel):
    model_config = ConfigDict(extra='forbid')
    items: list[ProviderConnectionRef] = Field(default_factory=list)


class ActionTemplatesList(BaseModel):
    model_config = ConfigDict(extra='forbid')
    items: list[ActionTemplateRef] = Field(default_factory=list)


class WatiTemplatesList(BaseModel):
    model_config = ConfigDict(extra='forbid')
    items: list[WatiTemplateRef] = Field(default_factory=list)
    error: str | None = None


class CohortDatasetsList(BaseModel):
    model_config = ConfigDict(extra='forbid')
    items: list[CohortDatasetRef] = Field(default_factory=list)


class NodeTypesList(BaseModel):
    model_config = ConfigDict(extra='forbid')
    items: list[NodeTypeRef] = Field(default_factory=list)


ProviderName = Literal['wati', 'bolna', 'sms', 'lsq', 'msg91', 'aisensy']


def contains_credential_fields(payload: Any) -> str | None:
    """Recursively walk `payload` and return the first credential-shaped
    field name found, or None.

    Used by the pack's `build_outcome` egress filter. Blocklist match is
    case-insensitive and only on dict keys (list values are walked).
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(key, str) and key.lower() in CREDENTIAL_FIELD_BLOCKLIST:
                return key
            hit = contains_credential_fields(value)
            if hit is not None:
                return hit
        return None
    if isinstance(payload, list):
        for item in payload:
            hit = contains_credential_fields(item)
            if hit is not None:
                return hit
    return None


__all__ = [
    'CREDENTIAL_FIELD_BLOCKLIST',
    'ProviderConnectionRef',
    'ActionTemplateRef',
    'WatiTemplateRef',
    'CohortDatasetRef',
    'NodeTypeRef',
    'ProviderConnectionsList',
    'ActionTemplatesList',
    'WatiTemplatesList',
    'CohortDatasetsList',
    'NodeTypesList',
    'ProviderName',
    'contains_credential_fields',
]
