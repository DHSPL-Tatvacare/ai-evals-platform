"""Launch-source resolver registry for source-bound scheduled workloads.

A source-bound workload (``launch_source != 'explicit_params'``) does not take
client-supplied params. Instead the create-schedule payload carries a
``source_id`` and the backend re-resolves the canonical launch params from that
source via a resolver registered for the workload's ``job_type``. The source
endpoint/resolver is the single authority — client params are ignored.

Generic framework primitive: no capability-specific knowledge lives here.
Concrete resolvers (e.g. a CRM connection resolver) register from their own
module via ``register_launch_source_resolver``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class LaunchSpec:
    """Canonical launch descriptor resolved from a source.

    ``params`` are the job params persisted on the schedule, ``schedule_key``
    the per-source uniqueness key, ``name`` a default display name used when the
    create payload leaves ``name`` blank.
    """

    params: dict
    schedule_key: str
    name: str


LaunchSourceResolver = Callable[..., Awaitable[LaunchSpec]]


_RESOLVERS: dict[str, LaunchSourceResolver] = {}


def register_launch_source_resolver(job_type: str, fn: LaunchSourceResolver) -> None:
    """Register the resolver that turns a ``source_id`` into a ``LaunchSpec``.

    ``fn`` is ``async (db, *, tenant_id, app_id, source_id) -> LaunchSpec`` and
    must raise ``ValueError`` on an unknown/invalid source_id. Idempotent
    re-registration overwrites the prior entry for the job_type.
    """
    _RESOLVERS[job_type] = fn


async def resolve_launch_source(
    db: AsyncSession,
    *,
    job_type: str,
    tenant_id: UUID,
    app_id: str,
    source_id: str,
) -> LaunchSpec:
    """Resolve canonical launch params for a source-bound workload.

    Raises ``ValueError`` if no resolver is registered for ``job_type``, and
    propagates any ``ValueError`` the resolver raises for an invalid source_id.
    """
    resolver = _RESOLVERS.get(job_type)
    if resolver is None:
        raise ValueError(f"No launch-source resolver registered for job_type {job_type!r}")
    return await resolver(db, tenant_id=tenant_id, app_id=app_id, source_id=source_id)
