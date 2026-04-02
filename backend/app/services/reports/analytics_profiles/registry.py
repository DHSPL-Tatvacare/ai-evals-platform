"""Backend-only analytics profile registry."""

from __future__ import annotations

from app.services.reports.analytics_profiles.base import AnalyticsProfile
from app.services.reports.analytics_profiles.inside_sales import (
    INSIDE_SALES_ANALYTICS_PROFILE,
)
from app.services.reports.analytics_profiles.kaira import KAIRA_ANALYTICS_PROFILE
from app.services.reports.analytics_profiles.voice_rx import VOICE_RX_ANALYTICS_PROFILE


_PROFILE_REGISTRY: dict[str, AnalyticsProfile] = {
    KAIRA_ANALYTICS_PROFILE.key: KAIRA_ANALYTICS_PROFILE,
    INSIDE_SALES_ANALYTICS_PROFILE.key: INSIDE_SALES_ANALYTICS_PROFILE,
    VOICE_RX_ANALYTICS_PROFILE.key: VOICE_RX_ANALYTICS_PROFILE,
}


def get_analytics_profile(profile_key: str) -> AnalyticsProfile | None:
    return _PROFILE_REGISTRY.get(profile_key)


def list_analytics_profiles() -> list[AnalyticsProfile]:
    return list(_PROFILE_REGISTRY.values())
