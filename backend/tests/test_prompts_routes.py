"""Prompt contract tests — Phase 1 data + Phase 3 versioned library."""

import os
import sys
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.prompt import Prompt
from app.models.mixins.shareable import Visibility
from app.schemas.prompt import PromptCreate, PromptResponse, PromptUpdate
from app.services.access_control import can_access, readable_scope_clause


def test_prompt_create_accepts_branch_key_and_visibility():
    payload = PromptCreate(
        appId="voice-rx",
        promptType="transcription",
        branchKey="branch-123",
        name="Transcript Prompt",
        prompt="Extract transcript",
        visibility="app",
    )

    dumped = payload.model_dump(by_alias=True)

    assert dumped["branchKey"] == "branch-123"
    assert dumped["visibility"] == Visibility.APP


def test_prompt_response_serializes_branch_metadata():
    prompt = Prompt(
        id=1,
        app_id="voice-rx",
        prompt_type="transcription",
        branch_key="branch-123",
        version=2,
        name="Transcript Prompt",
        prompt="Extract transcript",
        description="",
        is_default=False,
        visibility=Visibility.APP,
        forked_from=7,
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    payload = PromptResponse.model_validate(prompt).model_dump(by_alias=True, mode="json")

    assert payload["branchKey"] == "branch-123"
    assert payload["visibility"] == "app"
    assert payload["forkedFrom"] == 7


def test_prompt_model_uses_branch_aware_version_uniqueness():
    constraint_names = {constraint.name for constraint in Prompt.__table__.constraints}

    assert "uq_prompt_branch_version" in constraint_names
    assert "branch_key" in Prompt.__table__.columns


# ─── Phase 3: Fork, visibility, latest-per-branch ──────────────


def _user(tenant_id, user_id, app_access=()):
    return SimpleNamespace(
        tenant_id=tenant_id, user_id=user_id,
        app_access=frozenset(app_access),
    )


def _prompt(tenant_id, user_id, app_id="voice-rx", visibility=Visibility.PRIVATE, **kw):
    return Prompt(
        id=kw.get("id", 1),
        tenant_id=tenant_id, user_id=user_id,
        app_id=app_id, prompt_type="transcription",
        branch_key=kw.get("branch_key", str(uuid.uuid4())),
        version=kw.get("version", 1),
        name="test", prompt="test", description="",
        is_default=kw.get("is_default", False),
        source_type=None, visibility=visibility,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_fork_access_any_user_can_read_app_shared_prompt():
    """Any user with app access can fork (read) an app-shared prompt."""
    tid = uuid.uuid4()
    owner = uuid.uuid4()
    reader = uuid.uuid4()
    user = _user(tid, reader, app_access=("voice-rx",))
    prompt = _prompt(tid, owner, visibility=Visibility.APP)
    assert can_access(user, prompt, "fork") is True


def test_fork_access_denied_for_other_users_private_prompt():
    """Cannot fork another user's private prompt."""
    tid = uuid.uuid4()
    owner = uuid.uuid4()
    reader = uuid.uuid4()
    user = _user(tid, reader, app_access=("voice-rx",))
    prompt = _prompt(tid, owner, visibility=Visibility.PRIVATE)
    assert can_access(user, prompt, "fork") is False


def test_visibility_patch_denied_for_system_defaults():
    """System defaults cannot have visibility changed."""
    from app.constants import SYSTEM_TENANT_ID, SYSTEM_USER_ID
    user = _user(SYSTEM_TENANT_ID, SYSTEM_USER_ID, app_access=("voice-rx",))
    prompt = _prompt(SYSTEM_TENANT_ID, SYSTEM_USER_ID, visibility=Visibility.APP, is_default=True)
    # System assets are immutable — edit is denied
    assert can_access(user, prompt, "edit") is False


def test_visibility_patch_owner_can_share_private_prompt():
    """Owner can change visibility from private to app (share action)."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    user = _user(tid, uid, app_access=("voice-rx",))
    prompt = _prompt(tid, uid, visibility=Visibility.PRIVATE)
    assert can_access(user, prompt, "share") is True


def test_create_with_branch_key_preserves_it():
    """PromptCreate with explicit branchKey retains it in the dump."""
    payload = PromptCreate(
        appId="voice-rx",
        promptType="transcription",
        branchKey="my-branch",
        name="Test",
        prompt="text",
    )
    assert payload.branch_key == "my-branch"


def test_create_without_branch_key_defaults_to_none():
    """PromptCreate without branchKey defaults to None (route generates UUID)."""
    payload = PromptCreate(
        appId="voice-rx",
        promptType="transcription",
        name="Test",
        prompt="text",
    )
    assert payload.branch_key is None


def test_readable_scope_clause_includes_tenant_shared_and_system_prompt_rows():
    auth = _user(uuid.uuid4(), uuid.uuid4(), app_access=("voice-rx",))
    stmt = select(Prompt.id).where(readable_scope_clause(Prompt, auth))

    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    assert "prompts.user_id" in sql
    assert "prompts.visibility = 'APP'" in sql
    assert "prompts.tenant_id" in sql


def test_prompt_update_marks_content_changes_as_new_version_required():
    assert PromptUpdate(prompt="new text").requires_new_version() is True
    assert PromptUpdate(name="rename only").requires_new_version() is False
