"""seed workflow_llm_extract platform call-site default

Revision ID: 0078
Revises: 0077
Create Date: 2026-05-23

Adds the platform-default (``tenant_id IS NULL``) row for the
``workflow_llm_extract`` call site so the orchestration ``llm.extract`` node
resolves without an admin step. Mirrors the 0051 platform-default seed exactly:
catalog-FK gate, ON CONFLICT idempotency, schema-qualified raw SQL. Supersedes
the gitignored runbook SQL.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0078"
down_revision: Union[str, None] = "0077"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_log = logging.getLogger("alembic.runtime.migration")

# (call_site, provider, credential_name, model_or_deployment) — same convention as 0051.
_CALL_SITE = "workflow_llm_extract"
_PROVIDER = "gemini"
_CREDENTIAL = "default"
_MODEL = "gemini-2.5-flash"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def upgrade() -> None:
    bind = op.get_bind()
    catalog = bind.execute(
        sa.text(
            """
            SELECT 1 FROM analytics.ref_llm_models_catalog
             WHERE provider = :provider AND model = :model
             LIMIT 1
            """
        ),
        {"provider": _PROVIDER, "model": _MODEL},
    ).first()
    if not catalog:
        _log.warning(
            "0078: skipping platform default for call_site=%s — catalog row "
            "%s/%s missing; operator must configure via /platform/llm/defaults",
            _CALL_SITE, _PROVIDER, _MODEL,
        )
        return
    bind.execute(
        sa.text(
            """
            INSERT INTO platform.tenant_call_site_defaults
                (id, tenant_id, call_site, provider, credential_name,
                 model_or_deployment, created_at, updated_at)
            VALUES
                (:id, NULL, :call_site, :provider, :credential_name,
                 :model, :now, :now)
            ON CONFLICT ON CONSTRAINT uq_tenant_call_site_defaults DO NOTHING
            """
        ),
        {
            "id": uuid.uuid4(),
            "call_site": _CALL_SITE,
            "provider": _PROVIDER,
            "credential_name": _CREDENTIAL,
            "model": _MODEL,
            "now": _now(),
        },
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM platform.tenant_call_site_defaults "
            "WHERE tenant_id IS NULL AND call_site = :call_site"
        ).bindparams(call_site=_CALL_SITE)
    )
