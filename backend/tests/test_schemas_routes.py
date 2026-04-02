"""Phase 1 schema contract tests."""

import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.mixins.shareable import Visibility
from app.models.schema import Schema
from app.schemas.schema import SchemaCreate, SchemaResponse


def test_schema_create_accepts_branch_key_and_visibility():
    payload = SchemaCreate(
        appId="voice-rx",
        promptType="transcription",
        branchKey="schema-branch",
        name="Transcript Schema",
        schemaData={"type": "object"},
        visibility="app",
    )

    dumped = payload.model_dump(by_alias=True)

    assert dumped["branchKey"] == "schema-branch"
    assert dumped["visibility"] == Visibility.APP


def test_schema_response_serializes_branch_metadata():
    schema = Schema(
        id=1,
        app_id="voice-rx",
        prompt_type="transcription",
        branch_key="schema-branch",
        version=3,
        name="Transcript Schema",
        schema_data={"type": "object"},
        description="",
        is_default=False,
        visibility=Visibility.APP,
        forked_from=2,
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    payload = SchemaResponse.model_validate(schema).model_dump(by_alias=True, mode="json")

    assert payload["branchKey"] == "schema-branch"
    assert payload["visibility"] == "app"
    assert payload["forkedFrom"] == 2


def test_schema_model_uses_branch_aware_version_uniqueness():
    constraint_names = {constraint.name for constraint in Schema.__table__.constraints}

    assert "uq_schema_branch_version" in constraint_names
    assert "branch_key" in Schema.__table__.columns
