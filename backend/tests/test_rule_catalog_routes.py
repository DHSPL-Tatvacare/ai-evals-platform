"""Phase 1 shared-setting access rules for rule catalogs and LLM settings."""

import os
import sys
import uuid
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.mixins.shareable import Visibility
from app.models.setting import Setting
from app.services.access_control import can_access


def _user(*, tenant_id: uuid.UUID, user_id: uuid.UUID, app_access: tuple[str, ...]) -> SimpleNamespace:
    return SimpleNamespace(
        tenant_id=tenant_id,
        user_id=user_id,
        app_access=frozenset(app_access),
    )


def test_rule_catalog_shared_setting_can_be_created_for_app_scope():
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    asset = Setting(
        app_id="kaira-bot",
        key="rule-catalog",
        value={"rules": []},
        tenant_id=tenant_id,
        user_id=user_id,
        visibility=Visibility.SHARED,
    )
    user = _user(tenant_id=tenant_id, user_id=user_id, app_access=("kaira-bot",))

    assert can_access(user, asset, "create") is True


def test_llm_settings_remain_private_only():
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    asset = Setting(
        app_id="",
        key="llm-settings",
        value={"provider": "openai"},
        tenant_id=tenant_id,
        user_id=user_id,
        visibility=Visibility.SHARED,
    )
    user = _user(tenant_id=tenant_id, user_id=user_id, app_access=())

    assert can_access(user, asset, "create") is False
