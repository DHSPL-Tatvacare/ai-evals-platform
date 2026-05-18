"""Internal analytics profile definitions.

Profiles are backend-only. App config exposes only the profile key.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.app_analytics_config import AppAnalyticsConfig
from app.schemas.base import CamelModel


class CrossRunAdapter:
    analytics_model: type[CamelModel]

    def aggregate(
        self,
        runs_data: list[tuple[dict, dict]],
        all_runs_count: int,
        analytics_config: AppAnalyticsConfig | None = None,
        app_id: str | None = None,
    ) -> CamelModel:
        raise NotImplementedError

    def load_cached(self, payload: dict) -> CamelModel:
        return self.analytics_model.model_validate(payload)


@dataclass(frozen=True)
class AnalyticsProfile:
    key: str
    report_service_cls: type | None = None
    report_payload_model: type[CamelModel] | None = None
    cross_run_adapter: CrossRunAdapter | None = None
    cross_run_summary_narrator_cls: type | None = None
    cross_run_summary_model: type[CamelModel] | None = None
    # Phase 3 — every section id the producer pipeline (service + narrative
    # executor + composer) is guaranteed to be able to fill when its
    # preconditions are met. The Phase 1 boot validator asserts
    # ``declared_single_run_section_ids ⊇ app.config.analytics.single_run.sections[].id``
    # so a config change that adds a section the producer cannot satisfy fails
    # boot, not at the first user click.
    #
    # Empty tuple is the opt-out sentinel — used by cross-run-only profiles and
    # in-development profiles that have not yet enumerated their single-run
    # sections. The validator skips the check for these.
    #
    # Phase 5 fixture tests verify the declaration is *truthful at runtime*
    # (running the profile against a fixture run produces these ids); Phase 3
    # only covers the static contract.
    declared_single_run_section_ids: tuple[str, ...] = ()
