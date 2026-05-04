"""WatiService — POST WATI templated messages.

Per concierge spec §5.3:
  Base URL has tenant ID in path: https://live-mt-server.wati.io/{tenantId}
  Auth: Authorization: Bearer <token>
  Send: POST /api/v2/sendTemplateMessage?whatsappNumber=<E164-no-plus>
  Response: {localMessageId, whatsappMessageId, ...}

Tests monkeypatch _make_client to inject httpx.MockTransport (no respx dep).
4xx → WatiServiceError (non-retryable). 5xx / network → httpx.HTTPError (retry-safe).
"""
from __future__ import annotations

from typing import Any

import httpx


class WatiServiceError(RuntimeError):
    """Raised on 4xx — non-retryable client error from WATI."""


def _make_client(timeout: float) -> httpx.AsyncClient:
    """Hook for tests: monkeypatch this to inject httpx.MockTransport."""
    return httpx.AsyncClient(timeout=timeout)


class WatiService:
    def __init__(self, *, base_url: str, wati_tenant_id: str, api_token: str, timeout: float = 30.0):
        if not base_url or not wati_tenant_id or not api_token:
            raise ValueError("WatiService requires base_url, wati_tenant_id, api_token")
        self._url = f"{base_url.rstrip('/')}/{wati_tenant_id}"
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }
        self._timeout = timeout

    async def send_template(
        self,
        *,
        whatsapp_number: str,
        template_name: str,
        broadcast_name: str,
        parameters: list[dict[str, str]],
        channel_number: str | None = None,
    ) -> dict[str, Any]:
        url = f"{self._url}/api/v2/sendTemplateMessage"
        body: dict[str, Any] = {
            "template_name": template_name,
            "broadcast_name": broadcast_name,
            "parameters": parameters,
        }
        if channel_number:
            body["channel_number"] = channel_number

        async with _make_client(self._timeout) as client:
            resp = await client.post(
                url,
                params={"whatsappNumber": whatsapp_number},
                json=body,
                headers=self._headers,
            )
            if 400 <= resp.status_code < 500:
                try:
                    err_body = resp.json()
                except Exception:
                    err_body = {"text": resp.text[:200]}
                raise WatiServiceError(f"WATI {resp.status_code}: {err_body}")
            resp.raise_for_status()  # 5xx → httpx.HTTPStatusError (retry-safe)
            return resp.json()

    async def get_message_templates(self) -> dict[str, Any] | list[Any]:
        url = f"{self._url}/api/v2/getMessageTemplates"
        async with _make_client(self._timeout) as client:
            resp = await client.get(url, headers=self._headers)
            if 400 <= resp.status_code < 500:
                try:
                    err_body = resp.json()
                except Exception:
                    err_body = {"text": resp.text[:200]}
                raise WatiServiceError(f"WATI {resp.status_code}: {err_body}")
            resp.raise_for_status()
            return resp.json()

    async def list_message_templates_summary(self) -> list[dict[str, Any]]:
        """Phase 13/C.1 — fetch templates and normalise into the
        ``[{name, language, status, parameters}]`` shape the frontend
        picker consumes.

        WATI's payload varies between deployments — sometimes a list at
        the top, sometimes a dict with ``messageTemplates``/``templates``/
        ``data``/``result``. Parameter placeholders inside body components
        are extracted as the canonical ordered list of ``{{N}}`` numbered
        slots so the variable-mapping editor can drive off them.
        """
        payload = await self.get_message_templates()
        candidates: list[dict[str, Any]] = []
        if isinstance(payload, list):
            candidates = [item for item in payload if isinstance(item, dict)]
        elif isinstance(payload, dict):
            for key in ("messageTemplates", "templates", "data", "result"):
                value = payload.get(key)
                if isinstance(value, list):
                    candidates = [item for item in value if isinstance(item, dict)]
                    break

        out: list[dict[str, Any]] = []
        for candidate in candidates:
            name = (
                candidate.get("template_name")
                or candidate.get("templateName")
                or candidate.get("elementName")
                or candidate.get("name")
                or ""
            )
            if not name:
                continue
            out.append({
                "name": str(name),
                "language": str(
                    candidate.get("language")
                    or candidate.get("templateLanguage")
                    or ""
                ),
                "status": str(
                    candidate.get("status")
                    or candidate.get("templateStatus")
                    or ""
                ),
                "parameters": _extract_template_parameters(candidate),
            })
        return out


def _extract_template_parameters(candidate: dict[str, Any]) -> list[str]:
    """Return the ordered list of template placeholder names.

    Strategy:
      1. If the template carries a ``parameters`` / ``placeholders`` /
         ``variables`` list, take it verbatim. WATI templates that
         pre-declare names (e.g. ``["first_name", "city"]``) take this
         path.
      2. Otherwise scan ``components[].text`` (and a few legacy keys
         that surface the body string) for ``{{N}}`` placeholders and
         return them as ordered ``["1", "2", ...]`` strings, so the
         downstream variable-mapping editor at least knows the slot
         count.
    """
    for key in ("parameters", "placeholders", "variables"):
        value = candidate.get(key)
        if isinstance(value, list) and value:
            names: list[str] = []
            for item in value:
                if isinstance(item, str):
                    names.append(item)
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("key") or item.get("id")
                    if isinstance(name, str) and name:
                        names.append(name)
            if names:
                return names

    body_strings: list[str] = []
    components = candidate.get("components")
    if isinstance(components, list):
        for component in components:
            if isinstance(component, dict):
                text = component.get("text") or component.get("body")
                if isinstance(text, str):
                    body_strings.append(text)
    for legacy in ("body", "text", "message"):
        v = candidate.get(legacy)
        if isinstance(v, str):
            body_strings.append(v)

    import re
    found: list[str] = []
    seen: set[str] = set()
    for text in body_strings:
        for match in re.finditer(r"\{\{\s*([^}\s]+)\s*\}\}", text):
            slot = match.group(1).strip()
            if slot and slot not in seen:
                found.append(slot)
                seen.add(slot)
    return found
