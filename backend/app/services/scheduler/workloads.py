"""Platform-wide registry of schedule-enabled workloads.

A workload is a `(app_id, job_type)` pair that can be driven by the
scheduler. The registry also carries UI labels and the launch source
descriptor so the Create Schedule overlay knows which source list to show.

Workloads are populated by ``@register_job_handler(..., schedulable=True)``
in ``app.services.job_worker`` — that decorator is the single source of
truth. Do not call ``register_workload`` from import-time module bodies
anymore; add the policy to the handler decorator instead. The
``register_workload`` export stays public so tests / extensions that need
to register transient workloads can do so explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


LaunchSource = Literal["canonical_run", "canonical_config", "explicit_params"]


@dataclass(frozen=True)
class ScheduledWorkload:
    app_id: str
    job_type: str
    label: str
    description: str
    launch_source: LaunchSource = "explicit_params"
    source_list_endpoint: str | None = None
    default_params: dict[str, Any] = field(default_factory=dict)
    # True for workloads seeded by the platform (e.g. the daily cost
    # rollup) that users cannot create themselves — typically because
    # they are platform-wide (``app_id=""``) and fall outside the
    # pydantic ``min_length=1`` contract on ``ScheduledJobCreate.app_id``.
    # Hidden from the user-facing registry endpoint but still returned
    # by ``get_workload(app_id, job_type)`` so the scheduler engine and
    # admin tooling can look them up by key.
    platform_managed: bool = False


_REGISTRY: list[ScheduledWorkload] = []


def register_workload(workload: ScheduledWorkload) -> None:
    """Register a schedule-enabled workload. Idempotent on (app_id, job_type)."""
    key = (workload.app_id, workload.job_type)
    for existing in _REGISTRY:
        if (existing.app_id, existing.job_type) == key:
            return
    _REGISTRY.append(workload)


def get_workloads() -> list[ScheduledWorkload]:
    return list(_REGISTRY)


def get_workload(app_id: str, job_type: str) -> ScheduledWorkload | None:
    for workload in _REGISTRY:
        if workload.app_id == app_id and workload.job_type == job_type:
            return workload
    return None


def ensure_handler_workloads_registered() -> None:
    """Force-import ``app.services.job_worker`` so its ``@register_job_handler``
    decorators run and fill the workload registry.

    Callers (the registry route, tests) that read ``get_workloads()`` without
    first having imported the worker module need this shim — the decorator
    self-registers on import, so a single import side-effect is all that's
    required. The function is idempotent: re-importing a loaded module is
    a dict lookup.
    """
    import app.services.job_worker  # noqa: F401 — import is the side-effect
