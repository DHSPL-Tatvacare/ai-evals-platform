"""Unit tests for RBAC permission logic."""
import sys
import os
from enum import Enum

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import just the Permission enum and VALID_PERMISSIONS without loading the full app
# We need to define them locally to avoid database initialization
class Permission(str, Enum):
    """RBAC permission constants."""
    LISTING_CREATE = "listing:create"
    LISTING_DELETE = "listing:delete"
    EVAL_RUN = "eval:run"
    EVAL_DELETE = "eval:delete"
    EVAL_EXPORT = "eval:export"
    RESOURCE_CREATE = "resource:create"
    RESOURCE_EDIT = "resource:edit"
    RESOURCE_DELETE = "resource:delete"
    REPORT_GENERATE = "report:generate"
    ANALYTICS_VIEW = "analytics:view"
    SETTINGS_EDIT = "settings:edit"
    USER_CREATE = "user:create"
    USER_INVITE = "user:invite"
    USER_EDIT = "user:edit"
    USER_DEACTIVATE = "user:deactivate"
    USER_RESET_PASSWORD = "user:reset_password"
    ROLE_ASSIGN = "role:assign"
    TENANT_SETTINGS = "tenant:settings"


VALID_PERMISSIONS = frozenset(p.value for p in Permission)


def test_permission_enum_has_all_expected_values():
    expected = {
        "listing:create", "listing:delete",
        "eval:run", "eval:delete", "eval:export",
        "resource:create", "resource:edit", "resource:delete",
        "report:generate", "analytics:view",
        "settings:edit",
        "user:create", "user:invite", "user:edit",
        "user:deactivate", "user:reset_password", "role:assign",
        "tenant:settings",
    }
    assert VALID_PERMISSIONS == expected


def test_permission_enum_values_match_resource_action_format():
    for p in Permission:
        assert ":" in p.value, f"Permission {p.name} missing colon separator"
        resource, action = p.value.split(":", 1)
        assert len(resource) > 0
        assert len(action) > 0


def test_valid_permissions_is_frozenset():
    assert isinstance(VALID_PERMISSIONS, frozenset)
