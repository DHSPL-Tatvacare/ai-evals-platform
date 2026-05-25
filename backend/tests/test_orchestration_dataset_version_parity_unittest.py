"""Dataset version-parity additive surface: columns + relationships.

Pure-Python mapper introspection plus one live-DB round-trip proving the new
columns persist with their server defaults and that dataset↔version↔row
relationships navigate (eager-loaded — async lazy access raises MissingGreenlet).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.orm import selectinload

from app.models.orchestration import (
    CohortDataset,
    CohortDatasetRow,
    CohortDatasetVersion,
    CohortDefinition,
    CohortDefinitionVersion,
    Workflow,
    WorkflowVersion,
)


def test_parent_aggregates_expose_current_published_version_id():
    for parent in (Workflow, CohortDefinition, CohortDataset):
        assert "current_published_version_id" in inspect(parent).columns.keys()


def test_version_aggregates_expose_publish_lifecycle_columns():
    for version in (WorkflowVersion, CohortDefinitionVersion, CohortDatasetVersion):
        cols = inspect(version).columns.keys()
        assert "status" in cols
        assert "published_by" in cols
        assert "published_at" in cols


def test_version_number_column_name_not_unified():
    # Intentionally NOT unified: datasets keep ``version_number`` while
    # workflow/cohort use ``version``. Each carries its own int version column.
    assert "version" in inspect(WorkflowVersion).columns.keys()
    assert "version" in inspect(CohortDefinitionVersion).columns.keys()
    assert "version_number" in inspect(CohortDatasetVersion).columns.keys()


def test_dataset_version_communication_key_not_null():
    col = inspect(CohortDatasetVersion).columns["communication_key"]
    assert col.nullable is False


def test_dataset_relationship_navigation_exists():
    assert {"versions", "current_published_version"} <= set(
        inspect(CohortDataset).relationships.keys()
    )
    assert {"dataset", "rows"} <= set(
        inspect(CohortDatasetVersion).relationships.keys()
    )
    assert "version" in inspect(CohortDatasetRow).relationships.keys()


@pytest.mark.asyncio
async def test_dataset_version_parity_round_trip(db_session, seed_tenant_user_app):
    tenant_id, user_id, app_id = seed_tenant_user_app

    dataset = CohortDataset(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        app_id=app_id,
        name=f"dataset-{uuid.uuid4().hex[:8]}",
        description="version-parity round-trip fixture",
        created_by=user_id,
    )
    db_session.add(dataset)
    await db_session.flush()

    version = CohortDatasetVersion(
        id=uuid.uuid4(),
        dataset_id=dataset.id,
        tenant_id=tenant_id,
        version_number=1,
        communication_key="phone",
        source_type="csv",
        row_count=1,
        id_strategy="uuid",
        id_column=None,
        schema_descriptor={"columns": []},
        imported_by=user_id,
    )
    db_session.add(version)
    await db_session.flush()
    await db_session.refresh(version)
    assert version.status == "draft"

    row = CohortDatasetRow(
        dataset_version_id=version.id,
        row_seq=1,
        tenant_id=tenant_id,
        recipient_id="recipient-001",
        payload={"name": "alice"},
    )
    db_session.add(row)
    await db_session.flush()

    dataset.current_published_version_id = version.id
    await db_session.flush()

    loaded = (
        await db_session.scalars(
            select(CohortDataset)
            .where(CohortDataset.id == dataset.id)
            .options(
                selectinload(CohortDataset.versions),
                selectinload(CohortDataset.current_published_version),
            )
        )
    ).one()
    assert version.id in [v.id for v in loaded.versions]
    assert loaded.current_published_version.id == version.id

    await db_session.refresh(version, ["rows"])
    assert row.row_seq in [r.row_seq for r in version.rows]

    await db_session.refresh(row, ["version"])
    assert row.version.id == version.id
