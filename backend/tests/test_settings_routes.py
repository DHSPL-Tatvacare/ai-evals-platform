"""Settings contract tests — Phase 1 data contracts + Phase 2 resolution."""

import os
import sys
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.dialects import postgresql

from app.models.setting import Setting
from app.models.mixins.shareable import Visibility
from app.schemas.setting import SettingCreate, SettingResponse
from app.services.settings_upsert import build_setting_upsert_stmt


def test_setting_create_accepts_visibility_for_shared_contract_rows():
    payload = SettingCreate(
        appId="kaira-bot",
        key="adversarial-config",
        value={"version": 1},
        visibility="app",
    )

    assert payload.visibility == Visibility.APP
    assert payload.model_dump(by_alias=True)["visibility"] == Visibility.APP


def test_setting_response_serializes_share_metadata_in_camel_case():
    row = Setting(
        id=10,
        app_id="kaira-bot",
        key="rule-catalog",
        value={"rules": []},
        visibility=Visibility.APP,
        updated_by=uuid.uuid4(),
        shared_by=uuid.uuid4(),
        shared_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )

    payload = SettingResponse.model_validate(row).model_dump(by_alias=True, mode="json")

    assert payload["visibility"] == "app"
    assert "updatedBy" in payload
    assert "sharedBy" in payload
    assert "sharedAt" in payload


def test_setting_model_exposes_private_and_app_unique_indexes():
    index_names = {index.name for index in Setting.__table__.indexes}

    assert "uq_settings_private_scope" in index_names
    assert "uq_settings_app_scope" in index_names


# ─── Phase 2: Settings resolution + access tests ────────────────

from app.services.access_control import can_access


def _make_user(tenant_id, user_id, app_access=frozenset()):
    return SimpleNamespace(
        tenant_id=tenant_id,
        user_id=user_id,
        app_access=frozenset(app_access),
    )


def _make_setting(tenant_id, user_id, app_id, key, visibility):
    return Setting(
        id=99,
        tenant_id=tenant_id,
        user_id=user_id,
        app_id=app_id,
        key=key,
        value={},
        visibility=visibility,
        updated_at=datetime.now(timezone.utc),
    )


def test_app_member_can_read_shared_setting():
    """Any user with app access can read an app-shared setting."""
    tid = uuid.uuid4()
    owner = uuid.uuid4()
    reader = uuid.uuid4()
    user = _make_user(tid, reader, app_access=frozenset({"kaira-bot"}))
    asset = _make_setting(tid, owner, "kaira-bot", "adversarial-config", Visibility.APP)

    assert can_access(user, asset, "read") is True


def test_app_member_cannot_read_other_users_private_setting():
    """A user cannot read another user's private setting."""
    tid = uuid.uuid4()
    owner = uuid.uuid4()
    reader = uuid.uuid4()
    user = _make_user(tid, reader, app_access=frozenset({"kaira-bot"}))
    asset = _make_setting(tid, owner, "kaira-bot", "my-config", Visibility.PRIVATE)

    assert can_access(user, asset, "read") is False


def test_app_member_cannot_edit_shared_setting_unless_owner():
    """Only the owner of a shared setting can edit it (at this access-control level)."""
    tid = uuid.uuid4()
    owner = uuid.uuid4()
    other = uuid.uuid4()
    user = _make_user(tid, other, app_access=frozenset({"kaira-bot"}))
    asset = _make_setting(tid, owner, "kaira-bot", "rule-catalog", Visibility.APP)

    assert can_access(user, asset, "edit") is False


def test_llm_settings_cannot_be_created_as_app_visibility():
    """Creating llm-settings with app visibility must be denied."""
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    user = _make_user(tid, uid, app_access=frozenset({"voice-rx"}))
    asset = _make_setting(tid, uid, "", "llm-settings", Visibility.APP)

    assert can_access(user, asset, "create") is False


def test_app_shared_upsert_targets_shared_scope_not_owner_scope():
    stmt = build_setting_upsert_stmt(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        app_id="kaira-bot",
        key="rule-catalog",
        value={"rules": []},
        visibility=Visibility.APP,
        updated_by=uuid.uuid4(),
        forked_from=None,
        shared_by=uuid.uuid4(),
    )

    sql = str(stmt.compile(dialect=postgresql.dialect()))

    assert 'ON CONFLICT (tenant_id, app_id, key, visibility)' in sql
    assert "WHERE visibility = 'APP'" in sql


def test_private_upsert_targets_private_scope_including_owner():
    stmt = build_setting_upsert_stmt(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        app_id="voice-rx",
        key="llm-settings",
        value={"provider": "openai"},
        visibility=Visibility.PRIVATE,
        updated_by=uuid.uuid4(),
        forked_from=None,
    )

    sql = str(stmt.compile(dialect=postgresql.dialect()))

    assert 'ON CONFLICT (tenant_id, app_id, key, user_id, visibility)' in sql
    assert "WHERE visibility = 'PRIVATE'" in sql
