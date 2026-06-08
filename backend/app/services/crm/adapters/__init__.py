"""CRM-source adapters — provider-aware land + discover, registered into the shared registry.

Vendor modules are imported for their registration side effects so every entrypoint
(backend, worker, tests) that touches this package gets the full ``crm_source`` registry.
"""
from __future__ import annotations

from typing import Any

from app.services.orchestration.adapters import resolve_adapter
from app.services.crm.adapters.protocol import (
    CrmSourceAdapter,
    CrmTransport,
    DiscoveredObject,
    FetchPage,
    SourceRecordDraft,
)


def resolve_crm_adapter(*, vendor: str) -> Any:
    """The CRM-source adapter for a provider vendor (``crm_source`` capability)."""
    return resolve_adapter(capability="crm_source", vendor=vendor)


__all__ = [
    "CrmSourceAdapter",
    "CrmTransport",
    "DiscoveredObject",
    "FetchPage",
    "SourceRecordDraft",
    "resolve_crm_adapter",
]

# Kept last: register_adapter must exist before these import-for-side-effect lines run.
from app.services.crm.adapters import lsq as _lsq  # noqa: E402,F401
