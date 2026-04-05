"""Unit tests for RBAC permission logic."""
import importlib.util
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_catalog_path = Path(__file__).resolve().parents[1] / "app" / "auth" / "permission_catalog.py"
_catalog_spec = importlib.util.spec_from_file_location("permission_catalog", _catalog_path)
assert _catalog_spec and _catalog_spec.loader
_catalog_module = importlib.util.module_from_spec(_catalog_spec)
sys.modules["permission_catalog"] = _catalog_module
_catalog_spec.loader.exec_module(_catalog_module)

PERMISSION_GROUPS = _catalog_module.PERMISSION_GROUPS
VALID_PERMISSIONS = _catalog_module.VALID_PERMISSIONS
serialize_permission_catalog = _catalog_module.serialize_permission_catalog


def test_permission_enum_has_all_expected_values():
    expected = {
        "listing:create", "listing:delete",
        "eval:run", "eval:delete", "eval:export",
        "resource:create", "resource:edit", "resource:delete",
        "report:generate", "analytics:view",
        "settings:edit",
        "user:create", "user:invite", "user:edit",
        "user:deactivate", "user:reset_password", "role:assign",
    }
    assert VALID_PERMISSIONS == expected


def test_permission_enum_values_match_resource_action_format():
    for permission_id in VALID_PERMISSIONS:
        assert ":" in permission_id, f"Permission {permission_id} missing colon separator"
        resource, action = permission_id.split(":", 1)
        assert len(resource) > 0
        assert len(action) > 0


def test_valid_permissions_is_frozenset():
    assert isinstance(VALID_PERMISSIONS, frozenset)


def test_permission_catalog_groups_cover_every_grantable_permission_once():
    catalog_ids = {
        permission.id
        for group in PERMISSION_GROUPS
        for permission in group.permissions
    }
    assert catalog_ids == VALID_PERMISSIONS


def test_permission_catalog_serialization_excludes_removed_permissions():
    payload = serialize_permission_catalog()

    serialized_ids = {
        permission["id"]
        for group in payload["groups"]
        for permission in group["permissions"]
    }

    assert serialized_ids == VALID_PERMISSIONS
    assert "tenant:settings" not in serialized_ids
    assert "evaluator:promote" not in serialized_ids
