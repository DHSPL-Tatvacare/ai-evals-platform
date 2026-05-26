"""VoiceAdapter for Bolna — outbound AI voice calls + terminal-event reconciliation."""
from __future__ import annotations

import csv as _csv
import io as _io
import logging
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, ClassVar, Mapping, Optional

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orchestration import (
    WorkflowRunRecipientAction,
    WorkflowRunRecipientState,
)
from app.services.orchestration.adapters.canonical import (
    CancelDispatchOutcome,
    CancelDispatchResult,
    CanonicalVoiceEvent,
    CanonicalVoiceRequest,
    CanonicalVoiceResponse,
)
from app.services.orchestration.dispatch._reconciler import apply_terminal_event

_log = logging.getLogger(__name__)


class BolnaServiceError(RuntimeError):
    """4xx from Bolna — non-retryable, surfaced verbatim on the action row."""


_TERMINAL_STATUSES: frozenset[str] = frozenset({
    "completed", "answered", "success",
    "failed", "canceled", "cancelled",
    "no-answer", "rnr", "busy",
    "error", "stopped", "balance-low",
    "call-disconnected",
})
# "Didn't reach the person" outcomes — retry-worthy, routed like RNR. Includes
# call-disconnected (connected then dropped) so a non-conversation isn't treated
# as a hard failure. A normal-end call reports 'completed', not 'call-disconnected'.
_NO_REACH_TOKENS = ("no-answer", "rnr", "busy", "call-disconnected")
_COST_DIVISOR = Decimal("100")
_COST_PRECISION = Decimal("0.0001")


def _make_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """Hook for tests — monkeypatch to inject httpx.MockTransport."""
    return httpx.AsyncClient(timeout=timeout)


def _safe_message(resp: httpx.Response) -> Optional[str]:
    try:
        return resp.json().get("message")
    except Exception:
        return None


def _is_batch(action: Any) -> bool:
    # Dispatch mode rides on payload, not a vendor column.
    return (getattr(action, "payload", None) or {}).get("mode") == "batch"


def classify_outcome(status: Optional[str], status_reason: Optional[str]) -> str:
    # Returns bolna_answered/rnr/failed — outcome action_types preserved per
    # the "Logs page action_type breakdown" carve-out in CLAUDE.md.
    s = (status or "").lower()
    r = (status_reason or "").lower()
    if (
        s in ("completed", "answered", "success")
        and "no-answer" not in r and "rnr" not in r and "busy" not in r
    ):
        return "bolna_answered"
    if any(tok in s or tok in r for tok in _NO_REACH_TOKENS):
        return "bolna_rnr"
    return "bolna_failed"


def _canonical_outcome(action_type: str) -> str:
    # Vendor-agnostic outcome that lands in steps.<node_id>.voice_outcome.
    if action_type == "bolna_answered":
        return "answered"
    if action_type == "bolna_rnr":
        return "no_answer"
    return "failed"


def is_terminal(status: Optional[str]) -> bool:
    return bool(status) and status.lower() in _TERMINAL_STATUSES  # type: ignore[union-attr]


def _normalize_cost_scalar(value: Any) -> Any:
    # Bolna ships costs in subunits (27.04 = 0.2704 in major units).
    if value is None or isinstance(value, bool):
        return value
    try:
        numeric = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return value
    normalized = (numeric / _COST_DIVISOR).quantize(
        _COST_PRECISION, rounding=ROUND_HALF_UP,
    )
    return float(normalized)


def _normalize_cost_tree(value: Any) -> Any:
    # Bolna nests per-component costs; normalize every scalar leaf, keep shape.
    if isinstance(value, dict):
        return {k: _normalize_cost_tree(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_cost_tree(item) for item in value]
    return _normalize_cost_scalar(value)


def _extract_capture(event: dict[str, Any]) -> dict[str, Any]:
    # Bolna splits some fields between the top level and a telephony_data nest.
    telephony = event.get("telephony_data") if isinstance(event.get("telephony_data"), dict) else {}

    def pick(key: str, *fallbacks: str) -> Any:
        v = event.get(key)
        if v is not None:
            return v
        for f in fallbacks:
            v = event.get(f)
            if v is not None:
                return v
            v = telephony.get(f) if isinstance(telephony, dict) else None
            if v is not None:
                return v
        return telephony.get(key) if isinstance(telephony, dict) else None

    return {
        "transcript": pick("transcript"),
        "recording_url": pick("recording_url", "recordingUrl"),
        "duration_sec": pick("duration", "duration_seconds"),
        "total_cost": _normalize_cost_scalar(pick("total_cost", "cost")),
        "cost_breakdown": _normalize_cost_tree(pick("cost_breakdown")),
        "extracted_data": pick("extracted_data"),
        "error_message": pick("error_message", "error"),
        "hangup_reason": pick("hangup_reason", "status_reason"),
        "telephony_provider": pick("telephony_provider"),
    }


def _resolve_from_phone(
    *, override: Optional[str], connection_default: Optional[str],
) -> Optional[str]:
    # Per-call override > connection default > vendor agent default; empty delegates down.
    cleaned_override = (override or "").strip()
    if cleaned_override:
        return cleaned_override
    cleaned_default = (connection_default or "").strip()
    if cleaned_default:
        return cleaned_default
    return None


def _build_batch_csv(
    *, requests: list[CanonicalVoiceRequest], recipient_ids: list[str],
) -> bytes:
    # recipient_id is echoed so per-execution webhooks can correlate back to a workflow recipient.
    extras = sorted({k for req in requests for k in req.variables.keys()})
    columns = ["contact_number", "recipient_id", *extras]
    buf = _io.StringIO()
    writer = _csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    for rid, req in zip(recipient_ids, requests):
        row: dict[str, Any] = {
            "contact_number": req.contact,
            "recipient_id": rid,
        }
        for col in extras:
            row[col] = req.variables.get(col, "")
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


class BolnaAdapter:
    capability = "voice"
    vendor = "bolna"
    # Bolna paid-tier outbound concurrency cap.
    batch_threshold: ClassVar[Optional[int]] = 10

    async def place_call(
        self, *, connection: dict[str, Any], request: CanonicalVoiceRequest,
    ) -> CanonicalVoiceResponse:
        api_key = connection.get("api_key") or ""
        base_url = (connection.get("base_url") or "https://api.bolna.ai").rstrip("/")
        if not api_key:
            raise BolnaServiceError("Bolna connection missing api_key")

        from_phone = _resolve_from_phone(
            override=request.from_phone,
            connection_default=connection.get("from_phone"),
        )
        body: dict[str, Any] = {
            "agent_id": request.agent_id,
            "recipient_phone_number": request.contact,
            "user_data": {
                **request.variables,
                # Echoed so terminal webhooks can correlate back to the
                # workflow recipient even when batch is in play later.
                "recipient_id": request.variables.get("recipient_id", ""),
            },
        }
        if from_phone:
            body["from_phone_number"] = from_phone
        if request.bypass_call_guardrails:
            body["bypass_call_guardrails"] = True

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        async with _make_client() as client:
            resp = await client.post(f"{base_url}/call", json=body, headers=headers)
            if 400 <= resp.status_code < 500:
                try:
                    err = resp.json()
                except Exception:
                    err = {"text": resp.text[:200]}
                raise BolnaServiceError(f"Bolna {resp.status_code}: {err}")
            resp.raise_for_status()
            raw = resp.json() if resp.content else {}

        execution_id = str(raw.get("execution_id") or "")
        if not execution_id:
            raise BolnaServiceError(
                "Bolna /call response missing execution_id — cannot correlate inbound webhooks"
            )
        return CanonicalVoiceResponse(
            provider_correlation_id=execution_id,
            contact=request.contact,
            mode="single",
            raw=raw,
        )

    async def place_call_batch(
        self,
        *,
        connection: dict[str, Any],
        requests: list[CanonicalVoiceRequest],
        recipient_ids: list[str],
    ) -> list[CanonicalVoiceResponse]:
        if not requests:
            return []
        if len(requests) != len(recipient_ids):
            raise BolnaServiceError(
                "place_call_batch: requests and recipient_ids length mismatch"
            )
        api_key = connection.get("api_key") or ""
        base_url = (connection.get("base_url") or "https://api.bolna.ai").rstrip("/")
        if not api_key:
            raise BolnaServiceError("Bolna connection missing api_key")

        first = requests[0]
        agent_id = first.agent_id
        from_phone = _resolve_from_phone(
            override=first.from_phone,
            connection_default=connection.get("from_phone"),
        )

        csv_bytes = _build_batch_csv(requests=requests, recipient_ids=recipient_ids)
        data: dict[str, Any] = {"agent_id": agent_id}
        if from_phone:
            data["from_phone_numbers"] = from_phone
        if first.bypass_call_guardrails:
            data["bypass_call_guardrails"] = "true"

        headers = {"Authorization": f"Bearer {api_key}"}
        files = {"file": ("cohort.csv", _io.BytesIO(csv_bytes), "text/csv")}
        async with _make_client(timeout=60.0) as client:
            resp = await client.post(
                f"{base_url}/batches", data=data, files=files, headers=headers,
            )
            if 400 <= resp.status_code < 500:
                try:
                    err = resp.json()
                except Exception:
                    err = {"text": resp.text[:200]}
                raise BolnaServiceError(f"Bolna {resp.status_code}: {err}")
            resp.raise_for_status()
            raw = resp.json() if resp.content else {}

        batch_id = str(raw.get("batch_id") or "")
        if not batch_id:
            raise BolnaServiceError(
                "Bolna /batches response missing batch_id — cannot correlate inbound webhooks"
            )
        return [
            CanonicalVoiceResponse(
                provider_correlation_id=batch_id,
                contact=req.contact,
                mode="batch",
                raw=raw,
            )
            for req in requests
        ]

    async def list_agents(self, connection: dict[str, Any]) -> list[dict[str, Any]]:
        """Fetch all agents from GET /v2/agent/all, return normalised {id, name, status, type} list."""
        api_key = connection.get("api_key") or ""
        base_url = (connection.get("base_url") or "https://api.bolna.ai").rstrip("/")
        if not api_key:
            raise BolnaServiceError("Bolna connection missing api_key")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        async with _make_client() as client:
            resp = await client.get(f"{base_url}/v2/agent/all", headers=headers)
            if 400 <= resp.status_code < 500:
                try:
                    err = resp.json()
                except Exception:
                    err = {"text": resp.text[:200]}
                raise BolnaServiceError(f"Bolna {resp.status_code}: {err}")
            resp.raise_for_status()
            payload = resp.json()
        if isinstance(payload, dict) and "agents" in payload:
            payload = payload["agents"]
        if not isinstance(payload, list):
            raise BolnaServiceError(
                f"Bolna /v2/agent/all returned unexpected shape: {type(payload).__name__}"
            )
        out: list[dict[str, Any]] = []
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            out.append({
                "id": str(raw.get("id") or raw.get("agent_id") or ""),
                "name": str(raw.get("agent_name") or raw.get("name") or ""),
                "status": str(raw.get("agent_status") or raw.get("status") or ""),
                "type": str(raw.get("agent_type") or raw.get("type") or ""),
            })
        return out

    async def get_agent(self, connection: dict[str, Any], *, agent_id: str) -> dict[str, Any]:
        """Fetch a single agent from GET /v2/agent/{agent_id}."""
        if not agent_id:
            raise ValueError("BolnaAdapter.get_agent requires agent_id")
        api_key = connection.get("api_key") or ""
        base_url = (connection.get("base_url") or "https://api.bolna.ai").rstrip("/")
        if not api_key:
            raise BolnaServiceError("Bolna connection missing api_key")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        async with _make_client() as client:
            resp = await client.get(f"{base_url}/v2/agent/{agent_id}", headers=headers)
            if 400 <= resp.status_code < 500:
                try:
                    err = resp.json()
                except Exception:
                    err = {"text": resp.text[:200]}
                raise BolnaServiceError(f"Bolna {resp.status_code}: {err}")
            resp.raise_for_status()
            return resp.json()

    async def cancel_dispatch(
        self, *, connection: dict[str, Any], action: Any,
    ) -> CancelDispatchResult:
        # Single-call execution_id lives in the generic correlation column.
        execution_id = getattr(action, "provider_correlation_id", None)
        if not execution_id:
            return CancelDispatchResult(
                outcome=CancelDispatchOutcome.noop_already_terminal,
                provider_message="no execution_id on action",
            )
        base_url = (connection.get("base_url") or "https://api.bolna.ai").rstrip("/")
        headers = {"Authorization": f"Bearer {connection.get('api_key')}"}
        async with _make_client() as client:
            resp = await client.post(
                f"{base_url}/call/{execution_id}/stop", headers=headers,
            )
        if resp.status_code == 200:
            return CancelDispatchResult(
                outcome=CancelDispatchOutcome.stopped, provider_status_code=200,
            )
        if resp.status_code in (400, 404):
            return CancelDispatchResult(
                outcome=CancelDispatchOutcome.noop_already_delivered,
                provider_status_code=resp.status_code,
                provider_message=_safe_message(resp),
            )
        return CancelDispatchResult(
            outcome=CancelDispatchOutcome.provider_error,
            provider_status_code=resp.status_code,
            provider_message=_safe_message(resp),
        )

    async def cancel_batch(
        self, *, connection: dict[str, Any], batch_id: str,
    ) -> CancelDispatchResult:
        base_url = (connection.get("base_url") or "https://api.bolna.ai").rstrip("/")
        headers = {"Authorization": f"Bearer {connection.get('api_key')}"}
        async with _make_client() as client:
            resp = await client.post(
                f"{base_url}/batches/{batch_id}/stop", headers=headers,
            )
        if resp.status_code == 200:
            return CancelDispatchResult(
                outcome=CancelDispatchOutcome.cancelled, provider_status_code=200,
            )
        if resp.status_code == 404:
            return CancelDispatchResult(
                outcome=CancelDispatchOutcome.noop_already_terminal,
                provider_status_code=404,
                provider_message=_safe_message(resp),
            )
        return CancelDispatchResult(
            outcome=CancelDispatchOutcome.provider_error,
            provider_status_code=resp.status_code,
            provider_message=_safe_message(resp),
        )

    async def cancel_run_actions(
        self, *, connection: dict[str, Any], actions: list[Any],
    ) -> list[CancelDispatchResult]:
        # Batch dispatch is cancelled once at the batch level; only standalone
        # single-call executions get a per-call stop. ``payload.mode`` — not a
        # vendor column — distinguishes batch; batch_id is provider_correlation_id.
        results: list[CancelDispatchResult] = []
        batch_ids = {
            getattr(a, "provider_correlation_id", None)
            for a in actions
            if _is_batch(a) and getattr(a, "provider_correlation_id", None)
        }
        for bid in batch_ids:
            results.append(await self.cancel_batch(connection=connection, batch_id=str(bid)))
        for action in actions:
            if _is_batch(action):
                continue
            results.append(await self.cancel_dispatch(connection=connection, action=action))
        return results

    def normalize_webhook(self, raw: dict[str, Any]) -> CanonicalVoiceEvent:
        status = raw.get("status")
        status_reason = raw.get("status_reason")
        action_type = classify_outcome(status, status_reason)
        outcome = _canonical_outcome(action_type)
        capture = _extract_capture(raw)
        telephony = raw.get("telephony_data")
        telephony = telephony if isinstance(telephony, dict) else {}
        ctx = raw.get("context_details")
        ctx = ctx if isinstance(ctx, dict) else {}
        contact = str(
            raw.get("recipient_phone_number")
            or raw.get("recipient_phone")
            or raw.get("to")
            or telephony.get("to_number")
            or ctx.get("recipient_phone_number")
            or "",
        )
        execution_id = str(
            raw.get("id") or raw.get("execution_id") or raw.get("batch_id") or ""
        )
        duration = capture.get("duration_sec")
        try:
            duration_int = int(duration) if duration is not None else None
        except (TypeError, ValueError):
            duration_int = None
        return CanonicalVoiceEvent(
            outcome=outcome,
            contact=contact,
            provider_correlation_id=execution_id,
            duration_sec=duration_int,
            transcript=capture.get("transcript"),
            recording_url=capture.get("recording_url"),
            vendor_raw=raw,
        )

    def verify_signature(self, raw: bytes, headers: Mapping[str, str]) -> bool:  # noqa: ARG002
        # Bolna ships no HMAC; the per-connection URL token gates the route.
        return True

    def is_terminal(self, status: Optional[str]) -> bool:
        return is_terminal(status)

    async def fetch_execution(
        self, *, connection: dict[str, Any], execution_id: str,
    ) -> Optional[dict[str, Any]]:
        """Poll GET /executions/{id} — the PRIMARY reconciliation pull. None on 404."""
        api_key = connection.get("api_key") or ""
        base_url = (connection.get("base_url") or "https://api.bolna.ai").rstrip("/")
        if not api_key:
            raise BolnaServiceError("Bolna connection missing api_key")
        headers = {"Authorization": f"Bearer {api_key}"}
        async with _make_client() as client:
            resp = await client.get(f"{base_url}/executions/{execution_id}", headers=headers)
        if resp.status_code == 200:
            return resp.json() if resp.content else {}
        if resp.status_code == 404:
            return None
        raise BolnaServiceError(f"Bolna {resp.status_code}: {_safe_message(resp)}")

    async def fetch_batch_summary(
        self, *, connection: dict[str, Any], batch_id: str,
    ) -> Optional[dict[str, Any]]:
        """Cheap batch gate — GET /batches/{id}; carries execution_status counts. None on 404."""
        api_key = connection.get("api_key") or ""
        base_url = (connection.get("base_url") or "https://api.bolna.ai").rstrip("/")
        if not api_key:
            raise BolnaServiceError("Bolna connection missing api_key")
        headers = {"Authorization": f"Bearer {api_key}"}
        async with _make_client() as client:
            resp = await client.get(f"{base_url}/batches/{batch_id}", headers=headers)
        if resp.status_code == 200:
            return resp.json() if resp.content else {}
        if resp.status_code == 404:
            return None
        raise BolnaServiceError(f"Bolna {resp.status_code}: {_safe_message(resp)}")

    async def fetch_batch_executions(
        self, *, connection: dict[str, Any], batch_id: str,
        page_number: int = 1, page_size: int = 50,
    ) -> dict[str, Any]:
        """One page of GET /batches/{id}/executions — each row carries a per-call id + status."""
        api_key = connection.get("api_key") or ""
        base_url = (connection.get("base_url") or "https://api.bolna.ai").rstrip("/")
        if not api_key:
            raise BolnaServiceError("Bolna connection missing api_key")
        headers = {"Authorization": f"Bearer {api_key}"}
        params = {"page_number": page_number, "page_size": page_size}
        async with _make_client() as client:
            resp = await client.get(
                f"{base_url}/batches/{batch_id}/executions", params=params, headers=headers,
            )
        if resp.status_code == 200:
            body = resp.json() if resp.content else {}
            rows = body.get("data") or body.get("executions") or []
            return {"data": rows, "has_more": bool(body.get("has_more", False))}
        if resp.status_code == 404:
            return {"data": [], "has_more": False}
        raise BolnaServiceError(f"Bolna {resp.status_code}: {_safe_message(resp)}")

    async def reconcile_execution(
        self,
        db: AsyncSession,
        *,
        action: Any,
        node_id: Optional[str],
        execution: dict[str, Any],
    ) -> bool:
        """Shared terminal-event core — both the webhook and the poller call this.

        The outcome idempotency key is derived here from the per-execution id so
        both ingress paths produce byte-identical keys and can never duplicate a child.
        """
        status = execution.get("status")
        # Single terminality gate for both paths — the poller calls this on every
        # fetched execution, so a still-in-flight call must no-op without writing.
        if not is_terminal(status):
            return False
        action_type = classify_outcome(status, execution.get("status_reason"))
        canonical = _canonical_outcome(action_type)
        capture = {k: v for k, v in _extract_capture(execution).items() if v is not None}
        exec_id = str(execution.get("id") or execution.get("execution_id") or "unknown")
        child_idem = f"voice-outcome|{exec_id}|{action_type}"

        recipient_payload_patch: dict[str, Any] = {"voice_outcome": canonical}
        if capture.get("transcript") is not None:
            recipient_payload_patch["voice_transcript"] = capture["transcript"]
        if capture.get("duration_sec") is not None:
            try:
                recipient_payload_patch["voice_duration_sec"] = int(capture["duration_sec"])
            except (TypeError, ValueError):
                recipient_payload_patch["voice_duration_sec"] = capture["duration_sec"]
        if capture.get("recording_url") is not None:
            recipient_payload_patch["voice_recording_url"] = capture["recording_url"]

        response_patch: dict[str, Any] = {
            "provider_status": str(status).lower(),
            "provider_terminal": True,
            "voice_outcome": canonical,
            **capture,
            "last_event": execution,
        }
        return await apply_terminal_event(
            db,
            action=action,
            response_patch=response_patch,
            recipient_payload_patch=recipient_payload_patch,
            node_id=node_id,
            provider_status=str(status).lower(),
            child_action_type=action_type,
            child_idempotency_key=child_idem,
        )

    async def handle_webhook(
        self,
        db: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        app_id: str,  # noqa: ARG002
        payload: dict[str, Any],
    ) -> None:
        status = payload.get("status")
        if not is_terminal(status):
            return

        # The webhook (and GET /executions/{id}) key the execution under "id" and
        # the recipient under context_details.recipient_data.recipient_id; only the
        # /call dispatch response uses execution_id/user_data — keep them as fallbacks.
        execution_id = payload.get("execution_id") or payload.get("id")
        batch_id = payload.get("batch_id")
        ctx = payload.get("context_details")
        ctx = ctx if isinstance(ctx, dict) else {}
        rdata = ctx.get("recipient_data")
        rdata = rdata if isinstance(rdata, dict) else {}
        user_data = payload.get("user_data")
        user_data = user_data if isinstance(user_data, dict) else {}
        recipient_id_hint = rdata.get("recipient_id") or user_data.get("recipient_id")

        parent, node_id = await self._find_parent(
            db, tenant_id=tenant_id,
            execution_id=str(execution_id) if execution_id else None,
            batch_id=str(batch_id) if batch_id else None,
            recipient_id_hint=str(recipient_id_hint) if recipient_id_hint else None,
        )
        if parent is None:
            _log.warning(
                "bolna.webhook.no_match execution_id=%s batch_id=%s status=%s",
                execution_id, batch_id, status,
            )
            return

        await self.reconcile_execution(
            db, action=parent, node_id=node_id, execution=payload,
        )

    async def _find_parent(
        self,
        db: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        execution_id: Optional[str],
        batch_id: Optional[str],
        recipient_id_hint: Optional[str],
    ) -> tuple[Optional[WorkflowRunRecipientAction], Optional[str]]:
        from sqlalchemy import and_, func
        from app.models.orchestration import WorkflowRunNodeStep

        ttl_join_gate = or_(
            WorkflowRunRecipientState.ignore_webhooks_after.is_(None),
            WorkflowRunRecipientState.ignore_webhooks_after > func.now(),
        )
        base = (
            select(WorkflowRunRecipientAction, WorkflowRunNodeStep.node_id)
            .join(
                WorkflowRunNodeStep,
                WorkflowRunNodeStep.id == WorkflowRunRecipientAction.node_step_id,
            )
            .join(
                WorkflowRunRecipientState,
                and_(
                    WorkflowRunRecipientState.run_id == WorkflowRunRecipientAction.run_id,
                    WorkflowRunRecipientState.recipient_id == WorkflowRunRecipientAction.recipient_id,
                ),
            )
            .where(
                WorkflowRunRecipientAction.tenant_id == tenant_id,
                WorkflowRunRecipientAction.channel == "voice",
                WorkflowRunRecipientAction.action_type == "voice_queued",
                ttl_join_gate,
            )
        )

        # Single-call mode: provider_correlation_id == execution_id.
        if execution_id:
            q = base.where(
                WorkflowRunRecipientAction.provider_correlation_id == execution_id
            )
            rows = (await db.execute(q)).all()
            if len(rows) == 1:
                row = rows[0]
                return row[0], row[1]
            if len(rows) > 1:
                _log.warning(
                    "bolna.execution_id.multi_match execution_id=%s count=%d — refusing to route",
                    execution_id, len(rows),
                )
                return None, None

        # Batch mode: provider_correlation_id == batch_id, narrowed by
        # the recipient_id Bolna echoes back in user_data.
        if batch_id and recipient_id_hint:
            q = base.where(
                WorkflowRunRecipientAction.provider_correlation_id == batch_id,
                WorkflowRunRecipientAction.recipient_id == recipient_id_hint,
            )
            rows = (await db.execute(q)).all()
            if len(rows) == 1:
                row = rows[0]
                return row[0], row[1]
            if len(rows) > 1:
                _log.warning(
                    "bolna.batch.multi_match batch_id=%s recipient_id=%s count=%d",
                    batch_id, recipient_id_hint, len(rows),
                )
                return None, None
        return None, None


from app.services.orchestration.adapters import register_adapter  # noqa: E402

register_adapter(capability="voice", vendor="bolna", adapter=BolnaAdapter())


__all__ = ["BolnaAdapter", "BolnaServiceError", "classify_outcome", "is_terminal"]
