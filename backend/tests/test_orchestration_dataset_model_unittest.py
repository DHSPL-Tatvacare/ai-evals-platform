"""CohortDataset / CohortDatasetVersion / CohortDatasetRow ORM round-trip.

Live-DB via the shared ``db_session`` fixture. Asserts the three Phase-12
schema rows persist + can be selected back out via the parent → child FK.
Each test rolls back at teardown so no rows leak.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.orchestration import (
    CohortDataset,
    CohortDatasetRow,
    CohortDatasetVersion,
)


@pytest.mark.asyncio
async def test_dataset_version_rows_round_trip(db_session, seed_tenant_user_app):
    tenant_id, user_id, app_id = seed_tenant_user_app

    dataset = CohortDataset(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        app_id=app_id,
        name=f"dataset-{uuid.uuid4().hex[:8]}",
        description="round-trip test fixture",
        created_by=user_id,
    )
    db_session.add(dataset)
    await db_session.flush()

    version = CohortDatasetVersion(
        id=uuid.uuid4(),
        dataset_id=dataset.id,
        tenant_id=tenant_id,
        version_number=1,
        source_type="csv",
        source_filename="cohort.csv",
        source_byte_size=1024,
        row_count=2,
        id_strategy="uuid",
        id_column=None,
        schema_descriptor={"columns": []},
        imported_by=user_id,
    )
    db_session.add(version)
    await db_session.flush()

    db_session.add_all(
        [
            CohortDatasetRow(
                dataset_version_id=version.id,
                row_seq=1,
                tenant_id=tenant_id,
                recipient_id="recipient-001",
                payload={"name": "alice"},
            ),
            CohortDatasetRow(
                dataset_version_id=version.id,
                row_seq=2,
                tenant_id=tenant_id,
                recipient_id="recipient-002",
                payload={"name": "bob"},
            ),
        ]
    )
    await db_session.flush()

    rows = (
        await db_session.scalars(
            select(CohortDatasetRow)
            .where(CohortDatasetRow.dataset_version_id == version.id)
            .order_by(CohortDatasetRow.row_seq)
        )
    ).all()
    assert len(rows) == 2
    assert [r.recipient_id for r in rows] == ["recipient-001", "recipient-002"]
    assert rows[0].payload == {"name": "alice"}
    assert rows[1].payload == {"name": "bob"}
