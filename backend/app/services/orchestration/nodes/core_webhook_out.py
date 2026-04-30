"""core.webhook_out — POST/PUT arbitrary JSON to an external URL per recipient.

Body templating uses {{var}} placeholders against the recipient payload +
'recipient_id'. Failures emit 'failed' edge; successes emit 'success'.

The HTTP client is constructed via _make_client() so tests can monkeypatch
in an httpx.MockTransport without bringing in a respx dependency.
"""
from __future__ import annotations

from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from app.services.orchestration.node_protocol import (
    ActionDispatch,
    NodeResult,
    RecipientOutcome,
)
from app.services.orchestration.node_registry import register_node


class _Config(BaseModel):
    url: str
    method: Literal["POST", "PUT"] = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    body_template: str
    timeout_seconds: float = 10.0


def _render(template: str, vars: dict[str, Any]) -> str:
    """Minimal {{var}} substitution. Avoids Jinja dep for one node."""
    out = template
    for k, v in vars.items():
        out = out.replace("{{" + k + "}}", str(v))
    return out


def _make_client(timeout_seconds: float) -> httpx.AsyncClient:
    """Hook for tests: monkeypatch this to inject httpx.MockTransport."""
    return httpx.AsyncClient(timeout=timeout_seconds)


@register_node(workflow_type="*", node_type="core.webhook_out")
class _Handler:
    node_type = "core.webhook_out"
    config_schema = _Config
    output_edges = ["success", "failed"]
    category = "action"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        success: list[RecipientOutcome] = []
        failed: list[RecipientOutcome] = []

        async with _make_client(config.timeout_seconds) as client:
            async for rid, payload in input_cohort:
                vars = {**payload, "recipient_id": rid}
                body = _render(config.body_template, vars)
                idem = ctx.idempotency_key(rid, "webhook_out")
                results = await ctx.dispatch_actions([
                    ActionDispatch(
                        recipient_id=rid, channel="webhook",
                        action_type="webhook_out_posted",
                        idempotency_key=idem,
                        payload={"url": config.url, "body": body, "method": config.method},
                    )
                ])
                action_id = results[0].action_id
                if results[0].status != "pending":
                    if results[0].status == "success":
                        success.append(RecipientOutcome(recipient_id=rid))
                    else:
                        failed.append(RecipientOutcome(recipient_id=rid))
                    continue
                try:
                    resp = await client.request(
                        config.method, config.url, content=body, headers={
                            "Content-Type": "application/json",
                            **config.headers,
                        }
                    )
                    if 200 <= resp.status_code < 300:
                        await ctx.update_action_result(
                            action_id, status="success",
                            response={"status_code": resp.status_code, "body": resp.text[:4000]},
                        )
                        success.append(RecipientOutcome(recipient_id=rid))
                    else:
                        await ctx.update_action_result(
                            action_id, status="failed",
                            error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                        )
                        failed.append(RecipientOutcome(recipient_id=rid))
                except httpx.HTTPError as exc:
                    await ctx.update_action_result(
                        action_id, status="failed", error=repr(exc),
                    )
                    failed.append(RecipientOutcome(recipient_id=rid))

        return NodeResult(
            by_edge_label={"success": success, "failed": failed},
            summary={"success_count": len(success), "failed_count": len(failed)},
        )
