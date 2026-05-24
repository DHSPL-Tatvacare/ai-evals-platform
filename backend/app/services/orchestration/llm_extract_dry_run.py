"""Run the llm.extract node's own runtime over a single sample payload.

Powers the AI agent Test pane. Reuses the node's ``_build_prompt`` / ``_build_llm``
seams (parity with the live run) and the same ``workflow_llm_extract`` call site;
cost is tagged ``workflow_llm_extract:builder_test`` so builder tests roll up
separately from production runs without a schema change.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.orchestration.nodes import llm_extract as _node

_BUILDER_TEST_CALL_PURPOSE = "workflow_llm_extract:builder_test"


class _DryRunContext:
    """Minimal node-context stand-in: ``_build_llm`` reads db/tenant/app/user/job."""

    def __init__(self, db, tenant_id: uuid.UUID, user_id: uuid.UUID | None, app_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.app_id = app_id
        self.job_id = None


async def run_llm_extract_dry_run(
    *,
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    app_id: str,
    config: "_node._Config",
    sample: dict[str, Any],
) -> dict[str, Any]:
    from app.services.evaluators.schema_generator import generate_json_schema

    ctx = _DryRunContext(db, tenant_id, user_id, app_id)
    llm = await _node._build_llm(ctx, config)
    if hasattr(llm, "set_call_purpose"):
        llm.set_call_purpose(_BUILDER_TEST_CALL_PURPOSE)

    prompt = _node._build_prompt(config, sample)
    json_schema = generate_json_schema([f.model_dump() for f in config.output_schema])
    result = await llm.generate_json(prompt, system_prompt=None, json_schema=json_schema)
    return {"prompt": prompt, "result": result}
