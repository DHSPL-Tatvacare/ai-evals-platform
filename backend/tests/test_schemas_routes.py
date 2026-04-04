"""Schema contract tests — Phase 1 data + Phase 3 versioned library."""

import os
import sys
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.mixins.shareable import Visibility
from app.models.schema import Schema
from app.schemas.schema import SchemaCreate, SchemaResponse, SchemaUpdate
from app.services.access_control import can_access, readable_scope_clause


def test_schema_create_accepts_branch_key_and_visibility():
    payload = SchemaCreate(
        appId="voice-rx",
        promptType="transcription",
        branchKey="schema-branch",
        name="Transcript Schema",
        schemaData={"type": "object"},
        visibility="shared",
    )

    dumped = payload.model_dump(by_alias=True)

    assert dumped["branchKey"] == "schema-branch"
    assert dumped["visibility"] == Visibility.SHARED


def test_schema_create_accepts_legacy_app_visibility_input_but_normalizes_to_shared():
    payload = SchemaCreate(
        appId="voice-rx",
        promptType="transcription",
        name="Transcript Schema",
        schemaData={"type": "object"},
        visibility="app",
    )

    assert payload.visibility == Visibility.SHARED


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
    assert payload["visibility"] == "shared"
    assert payload["forkedFrom"] == 2


def test_schema_model_uses_branch_aware_version_uniqueness():
    constraint_names = {constraint.name for constraint in Schema.__table__.constraints}

    assert "uq_schema_branch_version" in constraint_names
    assert "branch_key" in Schema.__table__.columns


# ─── Phase 3: Fork, visibility, latest-per-branch ──────────────


def _user(tenant_id, user_id, app_access=()):
    return SimpleNamespace(
        tenant_id=tenant_id, user_id=user_id,
        app_access=frozenset(app_access),
    )


def _schema(tenant_id, user_id, app_id="voice-rx", visibility=Visibility.PRIVATE, **kw):
    return Schema(
        id=kw.get("id", 1),
        tenant_id=tenant_id, user_id=user_id,
        app_id=app_id, prompt_type="transcription",
        branch_key=kw.get("branch_key", str(uuid.uuid4())),
        version=kw.get("version", 1),
        name="test", schema_data={"type": "object"}, description="",
        is_default=kw.get("is_default", False),
        source_type=None, visibility=visibility,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_fork_access_any_user_can_read_shared_schema():
    tid = uuid.uuid4()
    owner = uuid.uuid4()
    reader = uuid.uuid4()
    user = _user(tid, reader, app_access=("voice-rx",))
    schema = _schema(tid, owner, visibility=Visibility.SHARED)
    assert can_access(user, schema, "fork") is True


def test_fork_access_denied_for_other_users_private_schema():
    tid = uuid.uuid4()
    owner = uuid.uuid4()
    reader = uuid.uuid4()
    user = _user(tid, reader, app_access=("voice-rx",))
    schema = _schema(tid, owner, visibility=Visibility.PRIVATE)
    assert can_access(user, schema, "fork") is False


def test_visibility_patch_owner_can_share_private_schema():
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    user = _user(tid, uid, app_access=("voice-rx",))
    schema = _schema(tid, uid, visibility=Visibility.PRIVATE)
    assert can_access(user, schema, "share") is True


def test_create_schema_with_branch_key_preserves_it():
    payload = SchemaCreate(
        appId="voice-rx",
        promptType="transcription",
        branchKey="my-branch",
        name="Test",
        schemaData={"type": "object"},
    )
    assert payload.branch_key == "my-branch"


def test_readable_scope_clause_includes_tenant_shared_and_system_schema_rows():
    auth = _user(uuid.uuid4(), uuid.uuid4(), app_access=("voice-rx",))
    stmt = select(Schema.id).where(readable_scope_clause(Schema, auth))

    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    assert "schemas.user_id" in sql
    assert "schemas.visibility IN ('SHARED', 'APP')" in sql
    assert "schemas.tenant_id" in sql


def test_schema_update_marks_content_changes_as_new_version_required():
    assert SchemaUpdate(schemaData={"type": "array"}).requires_new_version() is True
    assert SchemaUpdate(name="rename only").requires_new_version() is False
