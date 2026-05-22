"""llm.extract — run a prompt over each contact's payload and write structured fields back.

The LLM is resolved through the ``workflow_llm_extract`` call site (capability
gating + tenant defaults + platform fallback) — never a direct provider SDK.
For clinical workflows the tenant default for this call site is the data-residency
authority: an admin configures the in-region deployment as the default, and the
FE editor surfaces the constraint where the operator picks a provider override.
"""
from __future__ import annotations

import json
from typing import Any, Literal, Optional

import jsonschema
from pydantic import BaseModel, Field

from app.services.orchestration._config_strictness import strict_node_config_dict
from app.services.orchestration.node_protocol import NodeResult, RecipientOutcome
from app.services.orchestration.node_registry import register_node

_CALL_SITE = "workflow_llm_extract"
_USAGE_CALL_PURPOSE = "workflow_llm_extract"


class _ArrayItemProperty(BaseModel):
    model_config = strict_node_config_dict()
    key: str
    type: Literal["string", "number", "boolean"] = "string"
    description: str = ""


class _ArrayItemSchema(BaseModel):
    model_config = strict_node_config_dict()
    itemType: Literal["string", "number", "boolean", "object"] = "string"
    properties: list[_ArrayItemProperty] = Field(default_factory=list)


class EvaluatorOutputField(BaseModel):
    """Mirrors the frontend ``EvaluatorOutputField`` — one structured output field.

    ``displayMode`` / ``role`` / ``isMainMetric`` / ``thresholds`` are
    display-only keys the shared ``SchemaTable`` editor round-trips; extraction
    ignores them but they are declared so a verbatim FE schema validates.
    """

    model_config = strict_node_config_dict()

    key: str
    type: Literal["number", "text", "boolean", "array", "enum"] = "text"
    description: str = ""
    enumValues: list[str] = Field(default_factory=list)
    arrayItemSchema: Optional[_ArrayItemSchema] = None
    displayMode: Optional[str] = None
    role: Optional[str] = None
    isMainMetric: Optional[bool] = None
    thresholds: Optional[dict[str, float]] = None


class _Config(BaseModel):
    model_config = strict_node_config_dict()

    prompt: str = Field(
        "",
        description="Instruction sent to the model for each contact. Reference fields with {{field}}.",
    )
    output_schema: list[EvaluatorOutputField] = Field(
        default_factory=list,
        description="Structured fields the model must return — enforced as JSON Schema.",
    )
    input_template: Optional[str] = Field(
        None,
        description="Per-contact context rendered from {{field}} placeholders. Falls back to the whole payload as JSON.",
    )
    output_namespace: str = Field(
        "",
        description="Payload key the extracted object is written under. Defaults to the node id.",
    )
    provider_override: Optional[str] = Field(
        None,
        description="Pin a provider for this node. Clinical workflows must use an approved in-region provider.",
    )
    model_override: Optional[str] = Field(
        None,
        description="Pin a model for this node. Resolved against the tenant's configured deployments.",
    )
    concurrency: int = Field(
        1, ge=1, le=20,
        description="How many contacts to process in parallel.",
    )
    inter_call_delay: float = Field(
        0.0, ge=0.0,
        description="Seconds to stagger between starting each contact (rate limiting).",
    )


def _render_template(template: str, payload: dict[str, Any]) -> str:
    out = template
    for key, value in payload.items():
        token = "{{" + key + "}}"
        if token in out:
            out = out.replace(token, "" if value is None else str(value))
    return out


def _build_prompt(config: _Config, payload: dict[str, Any]) -> str:
    if config.input_template:
        context = _render_template(config.input_template, payload)
        return _render_template(config.prompt, payload) + ("\n\n" + context if context else "")
    rendered = _render_template(config.prompt, payload)
    return f"{rendered}\n\n{json.dumps(payload, default=str, ensure_ascii=False)}"


async def _run_bounded_no_cancel(items, worker, *, concurrency, inter_item_delay):
    """Bounded-parallel runner for job_id=None mode (no cancellation poller).

    Same in-order results + per-item exception capture as ``run_parallel``,
    minus the ``is_job_cancelled`` DB checks that have no job to query.
    """
    import asyncio

    total = len(items)
    results: list[Any] = [None] * total
    semaphore = asyncio.Semaphore(concurrency)
    delay_lock = asyncio.Lock() if inter_item_delay > 0 else None

    async def _run_one(index: int, item):
        if delay_lock and index > 0:
            async with delay_lock:
                await asyncio.sleep(inter_item_delay)
        async with semaphore:
            try:
                results[index] = await worker(index, item)
            except BaseException as exc:  # noqa: BLE001 — captured like run_parallel
                results[index] = exc

    if concurrency <= 1:
        for i, item in enumerate(items):
            await _run_one(i, item)
    else:
        await asyncio.gather(*(_run_one(i, item) for i, item in enumerate(items)))
    return results


async def _build_llm(ctx, config: _Config):
    """Resolve the workflow_llm_extract call site into a LoggingLLMWrapper.

    Local imports keep the heavy LLM stack out of module import so node tests
    can monkeypatch this seam without pulling it in.
    """
    from app.services.evaluators.llm_base import LoggingLLMWrapper, create_llm_provider
    from app.services.evaluators.runner_utils import make_usage_callback
    from app.services.llm_credentials import resolve_llm_call

    resolved = await resolve_llm_call(
        ctx.db, ctx.tenant_id, _CALL_SITE,
        provider_override=config.provider_override or None,
        model_override=config.model_override or None,
    )

    factory_kwargs: dict[str, Any] = {}
    if resolved.provider == "azure_openai":
        factory_kwargs["azure_endpoint"] = resolved.credentials.extra_config.get("base_url") or ""
        factory_kwargs["api_version"] = (
            resolved.api_version
            or resolved.credentials.extra_config.get("api_version")
            or "2025-03-01-preview"
        )

    inner = create_llm_provider(
        provider=resolved.provider,
        model_name=resolved.model,
        api_key=resolved.credentials.secret.get("api_key", ""),
        service_account_path=resolved.credentials.service_account_path or "",
        **factory_kwargs,
    )
    usage_cb = make_usage_callback(
        tenant_id=ctx.tenant_id,
        user_id=getattr(ctx, "user_id", None),
        app_id=ctx.app_id,
        owner_type="job",
        owner_id=ctx.job_id,
        default_call_purpose=_USAGE_CALL_PURPOSE,
    )
    return LoggingLLMWrapper(inner, usage_callback=usage_cb)


@register_node(workflow_type="*", node_type="llm.extract")
class _Handler:
    node_type = "llm.extract"
    config_schema = _Config
    output_edges = ["success", "error"]
    category = "mutation"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        from app.services.evaluators.schema_generator import generate_json_schema

        namespace = config.output_namespace or ctx.current_node_id
        json_schema = generate_json_schema([f.model_dump() for f in config.output_schema])

        # Resume idempotency: a recipient already carrying the namespace was
        # extracted in a prior partial run — keep it, never re-call the model.
        recipients: list[tuple[str, dict[str, Any]]] = []
        skipped = 0
        async for rid, payload in input_cohort:
            if namespace in payload:
                skipped += 1
                continue
            recipients.append((rid, payload))

        if not recipients:
            return NodeResult(
                by_output_id={"success": [], "error": []},
                summary={"success_count": 0, "error_count": 0, "skipped_count": skipped},
            )

        llm = await _build_llm(ctx, config)

        async def _worker(_index: int, item: tuple[str, dict[str, Any]]) -> RecipientOutcome:
            rid, payload = item
            prompt = _build_prompt(config, payload)
            extracted = await llm.generate_json(
                prompt, system_prompt=None, json_schema=json_schema,
            )
            jsonschema.validate(instance=extracted, schema=json_schema)
            return RecipientOutcome(recipient_id=rid, payload_delta={namespace: extracted})

        if ctx.job_id is None:
            # Test/None mode: no job to cancel against — bypass the cancellation
            # poller (which opens a DB session) and run with the same bounded
            # parallelism locally. Mirrors NodeContext.is_cancelled tolerating None.
            results = await _run_bounded_no_cancel(
                recipients, _worker,
                concurrency=config.concurrency,
                inter_item_delay=config.inter_call_delay,
            )
        else:
            from app.services.evaluators.parallel_engine import run_parallel

            results = await run_parallel(
                recipients,
                _worker,
                concurrency=config.concurrency,
                job_id=ctx.job_id,
                tenant_id=ctx.tenant_id,
                inter_item_delay=config.inter_call_delay,
            )

        success: list[RecipientOutcome] = []
        error: list[RecipientOutcome] = []
        for (rid, _payload), outcome in zip(recipients, results):
            if isinstance(outcome, BaseException):
                error.append(RecipientOutcome(recipient_id=rid))
            else:
                success.append(outcome)

        return NodeResult(
            by_output_id={"success": success, "error": error},
            summary={
                "success_count": len(success),
                "error_count": len(error),
                "skipped_count": skipped,
            },
        )


__all__ = ["EvaluatorOutputField", "_Config", "_Handler"]
