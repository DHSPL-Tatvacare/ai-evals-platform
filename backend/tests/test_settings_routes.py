"""Phase 1 settings contract tests."""

import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.setting import Setting
from app.models.mixins.shareable import Visibility
from app.schemas.setting import SettingCreate, SettingResponse


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
