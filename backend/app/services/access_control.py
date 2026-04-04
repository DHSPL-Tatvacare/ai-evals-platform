"""Ownership and visibility checks shared by harmonized asset routes."""

from typing import Literal, Protocol, runtime_checkable

from sqlalchemy import and_, or_

from app.constants import SYSTEM_TENANT_ID, SYSTEM_USER_ID
from app.models.mixins.shareable import Visibility, shared_visibility_values

AccessAction = Literal["read", "create", "edit", "delete", "share", "unshare", "fork"]


@runtime_checkable
class AccessUser(Protocol):
    tenant_id: object
    user_id: object
    app_access: frozenset[str]


@runtime_checkable
class ShareableAsset(Protocol):
    tenant_id: object
    user_id: object
    app_id: str | None
    visibility: Visibility | str
    key: str | None


def _normalized_visibility(asset: ShareableAsset) -> str:
    normalized = Visibility.normalize(asset.visibility)
    if normalized is None:
        raise ValueError("Shareable assets must define visibility")
    return normalized.value


def is_shared_visibility(value: Visibility | str | None) -> bool:
    normalized = Visibility.normalize(value)
    return normalized == Visibility.SHARED


def shared_visibility_clause(column):
    """SQLAlchemy clause covering canonical and legacy shared rows."""

    return column.in_(shared_visibility_values())


def _is_system_asset(asset: ShareableAsset) -> bool:
    return asset.tenant_id == SYSTEM_TENANT_ID and asset.user_id == SYSTEM_USER_ID


def _has_app_access(user: AccessUser, asset: ShareableAsset) -> bool:
    if asset.app_id in (None, ""):
        return True
    return asset.app_id in user.app_access


def _is_owner(user: AccessUser, asset: ShareableAsset) -> bool:
    return user.tenant_id == asset.tenant_id and user.user_id == asset.user_id


def _is_private_only_setting(asset: ShareableAsset) -> bool:
    return getattr(asset, "key", None) == "llm-settings"


def can_access(user: AccessUser, asset: ShareableAsset, action: AccessAction) -> bool:
    """Answer ownership and visibility questions after route permission checks pass."""

    visibility = _normalized_visibility(asset)

    if _is_private_only_setting(asset) and visibility != Visibility.PRIVATE.value:
        return False

    if action == "create":
        if not _has_app_access(user, asset):
            return False
        if _is_private_only_setting(asset):
            return user.tenant_id == asset.tenant_id and visibility == Visibility.PRIVATE.value
        return user.tenant_id == asset.tenant_id and visibility in {
            Visibility.PRIVATE.value,
            Visibility.SHARED.value,
        }

    if action == "read":
        if not _has_app_access(user, asset):
            return False
        if visibility == Visibility.PRIVATE.value:
            return _is_owner(user, asset)
        if visibility == Visibility.SHARED.value:
            return user.tenant_id == asset.tenant_id or _is_system_asset(asset)
        return False

    if action == "fork":
        return can_access(user, asset, "read")

    if _is_system_asset(asset):
        return False

    if visibility == Visibility.PRIVATE.value:
        return _is_owner(user, asset)

    if visibility == Visibility.SHARED.value:
        return _is_owner(user, asset) and _has_app_access(user, asset)

    return False


def readable_scope_clause(model, user: AccessUser):
    """SQLAlchemy clause for rows the user may read under the harmonized model."""

    return or_(
        and_(model.tenant_id == user.tenant_id, model.user_id == user.user_id),
        and_(model.tenant_id == user.tenant_id, shared_visibility_clause(model.visibility)),
        and_(
            model.tenant_id == SYSTEM_TENANT_ID,
            model.user_id == SYSTEM_USER_ID,
            shared_visibility_clause(model.visibility),
        ),
    )
