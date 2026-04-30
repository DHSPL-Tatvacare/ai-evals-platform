"""LSQ writer for orchestration outcomes.

Per concierge spec §5.6 invariant: REUSES the existing LSQ auth params,
base URL, and rate limiter from backend/app/services/lsq_client.py.
Does not introduce a parallel auth or rate-limit layer.

Sets postUpdatedLead=false to prevent self-triggering feedback loops on
inbound LSQ webhooks.

The existing lsq_client API is:
  LSQ_BASE_URL          (module-level)
  _auth_params()        (module-level — returns {accessKey, secretKey})
  _rate_limited_request(client, method, url, **kwargs) — does the request
                        with global pacing + bounded retries

Tests monkeypatch lsq._make_client to inject httpx.MockTransport, and
monkeypatch lsq_client._auth_params + lsq_client.LSQ_BASE_URL for predictability.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from app.services import lsq_client as _lsq_client


class LsqWriteError(RuntimeError):
    pass


def _make_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """Hook for tests: monkeypatch this to inject httpx.MockTransport."""
    return httpx.AsyncClient(timeout=timeout)


def _base_url() -> str:
    return _lsq_client.LSQ_BASE_URL.rstrip("/")


def _auth_params() -> dict[str, str]:
    return _lsq_client._auth_params()


class LsqWriter:
    """Async POSTs to LSQ Lead.Update and ProspectActivity.Create.

    Construction takes no args — credentials and rate limiter are module-level
    in lsq_client (existing pattern).
    """

    async def update_stage(self, *, prospect_id: str, stage: str) -> None:
        url = f"{_base_url()}/LeadManagement.svc/Lead.Update"
        params = {**_auth_params(), "leadId": prospect_id, "postUpdatedLead": "false"}
        body = [{"Attribute": "ProspectStage", "Value": stage}]
        async with _make_client() as client:
            try:
                await _lsq_client._rate_limited_request(
                    client, "POST", url, params=params, json=body,
                )
            except _lsq_client.LsqRequestError as exc:
                raise LsqWriteError(
                    f"LSQ Lead.Update failed (status={exc.status_code}): {exc}"
                ) from exc

    async def log_activity(
        self,
        *,
        prospect_id: str,
        activity_event: int,
        note: str,
        fields: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        url = f"{_base_url()}/ProspectActivity.svc/Create"
        params = _auth_params()
        body = {
            "RelatedProspectId": prospect_id,
            "ActivityEvent": activity_event,
            "ActivityNote": note,
            "Fields": fields or [],
        }
        async with _make_client() as client:
            try:
                await _lsq_client._rate_limited_request(
                    client, "POST", url, params=params, json=body,
                )
            except _lsq_client.LsqRequestError as exc:
                raise LsqWriteError(
                    f"LSQ ProspectActivity.Create failed (status={exc.status_code}): {exc}"
                ) from exc
