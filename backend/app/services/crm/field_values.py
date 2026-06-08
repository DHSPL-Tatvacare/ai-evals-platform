"""Distinct observed values for a source field, read from the landed tape.

Feeds the editor's exhaustive value-map: the operator maps every value the CRM actually
emits to a canonical value, so a resolved enum column never holds an illegal value.
"""
from __future__ import annotations

import uuid

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import CrmSourceRecord

_DEFAULT_LIMIT = 200


async def distinct_field_values(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    connection_id: uuid.UUID,
    record_type: str,
    field: str,
    limit: int = _DEFAULT_LIMIT,
) -> list[str]:
    """Distinct non-null string values of ``field`` across this connection's landed records."""
    value = CrmSourceRecord.raw_payload[field].astext
    rows = await db.execute(
        select(distinct(value)).where(
            CrmSourceRecord.tenant_id == tenant_id,
            CrmSourceRecord.app_id == app_id,
            CrmSourceRecord.connection_id == connection_id,
            CrmSourceRecord.record_type == record_type,
            value.isnot(None),
        ).order_by(value).limit(limit)
    )
    return [r[0] for r in rows.all()]


__all__ = ["distinct_field_values"]
