"""Shared DTOs for Inside Sales dataset resolution.

The serving layer reads from the Postgres source mirror only — listing routes,
suggestions, and the eval runner all consume the dataclasses below. Filtering
is column-direct (case-insensitive on raw text columns); there is no
date-window or shadow-normalized contract anymore.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


CallDatasetScope = Literal["page", "all"]
CallSelectionMode = Literal["all", "sample", "specific"]


@dataclass(frozen=True)
class ResolvedDatasetPage:
    records: list[dict[str, Any]]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True)
class ResolvedCallSelection:
    records: list[dict[str, Any]]
    skipped_evaluated: int
    skipped_no_recording: int


@dataclass(frozen=True)
class InsideSalesCallFilters:
    agents: tuple[str, ...] = ()
    prospect_ids: tuple[str, ...] = ()
    direction: str | None = None
    status: str | None = None
    duration_min: int | None = None
    duration_max: int | None = None
    has_recording: bool | None = None
    event_codes: tuple[int, ...] | None = None


@dataclass(frozen=True)
class InsideSalesLeadFilters:
    agents: tuple[str, ...] = ()
    stage: tuple[str, ...] = ()
    mql_min: int | None = None
    condition: tuple[str, ...] = ()
    city: tuple[str, ...] = ()
    prospect_ids: tuple[str, ...] = ()
    phones: tuple[str, ...] = ()
    plan_names: tuple[str, ...] = ()
    q: str | None = None
