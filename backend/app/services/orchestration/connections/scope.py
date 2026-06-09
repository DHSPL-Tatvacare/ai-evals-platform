"""Shared app-scope predicate for provider-connection lookups.

A connection reaches an app when it is the home app, the connection is
tenant-wide, or the app is listed in ``app_scopes``. Applied at every
connection lookup site (resolver, builder picker, admin list, provider
listings) so scope semantics cannot drift between them.
"""
from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.sql.elements import ColumnElement

from app.models.provider_connection import ProviderConnection


def connection_app_scope_clause(app_id: str) -> ColumnElement[bool]:
    return or_(
        ProviderConnection.app_id == app_id,
        ProviderConnection.tenant_wide.is_(True),
        ProviderConnection.app_scopes.contains([app_id]),
    )


__all__ = ["connection_app_scope_clause"]
