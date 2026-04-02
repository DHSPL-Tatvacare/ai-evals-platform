"""Phase 1 evaluator contract tests."""

import os
import sys
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.constants import SYSTEM_TENANT_ID, SYSTEM_USER_ID
from app.models.evaluator import Evaluator
from app.models.mixins.shareable import Visibility
from app.schemas.evaluator import EvaluatorResponse
from app.services.access_control import can_access


def _user(*, tenant_id: uuid.UUID, user_id: uuid.UUID, app_access: tuple[str, ...]) -> SimpleNamespace:
    return SimpleNamespace(
        tenant_id=tenant_id,
        user_id=user_id,
        app_access=frozenset(app_access),
    )


def test_can_access_private_evaluator_for_owner_only():
    tenant_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    asset = Evaluator(
        app_id="kaira-bot",
        name="Private Eval",
        prompt="prompt",
        tenant_id=tenant_id,
        user_id=owner_id,
        visibility=Visibility.PRIVATE,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    owner = _user(tenant_id=tenant_id, user_id=owner_id, app_access=("kaira-bot",))
    other = _user(tenant_id=tenant_id, user_id=uuid.uuid4(), app_access=("kaira-bot",))

    assert can_access(owner, asset, "read") is True
    assert can_access(other, asset, "read") is False


def test_can_access_app_shared_evaluator_for_same_tenant_reader():
    tenant_id = uuid.uuid4()
    asset = Evaluator(
        app_id="kaira-bot",
        name="Shared Eval",
        prompt="prompt",
        tenant_id=tenant_id,
        user_id=uuid.uuid4(),
        visibility=Visibility.APP,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    reader = _user(tenant_id=tenant_id, user_id=uuid.uuid4(), app_access=("kaira-bot",))

    assert can_access(reader, asset, "read") is True


def test_can_access_system_seeded_evaluator_for_app_reader():
    asset = Evaluator(
        app_id="kaira-bot",
        name="System Eval",
        prompt="prompt",
        tenant_id=SYSTEM_TENANT_ID,
        user_id=SYSTEM_USER_ID,
        visibility=Visibility.APP,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    reader = _user(tenant_id=uuid.uuid4(), user_id=uuid.uuid4(), app_access=("kaira-bot",))

    assert can_access(reader, asset, "read") is True


def test_can_access_denies_system_seeded_evaluator_edit():
    asset = Evaluator(
        app_id="kaira-bot",
        name="System Eval",
        prompt="prompt",
        tenant_id=SYSTEM_TENANT_ID,
        user_id=SYSTEM_USER_ID,
        visibility=Visibility.APP,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    reader = _user(tenant_id=uuid.uuid4(), user_id=uuid.uuid4(), app_access=("kaira-bot",))

    assert can_access(reader, asset, "edit") is False


def test_evaluator_response_keeps_legacy_fields_as_derived_compatibility_output():
    evaluator = Evaluator(
        id=uuid.uuid4(),
        app_id="kaira-bot",
        name="Compatibility Eval",
        prompt="prompt",
        tenant_id=SYSTEM_TENANT_ID,
        user_id=SYSTEM_USER_ID,
        visibility=Visibility.APP,
        output_schema=[{"key": "score", "displayMode": "header"}],
        linked_rule_ids=["rule-1"],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    payload = EvaluatorResponse.model_validate(evaluator).model_dump(by_alias=True, mode="json")

    assert payload["visibility"] == "app"
    assert payload["linkedRuleIds"] == ["rule-1"]
    assert payload["isGlobal"] is True
    assert payload["isBuiltIn"] is True
    assert payload["showInHeader"] is True
