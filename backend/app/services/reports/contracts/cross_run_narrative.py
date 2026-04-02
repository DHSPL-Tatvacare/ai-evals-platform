"""Canonical cross-run narrative contract."""

from __future__ import annotations

from typing import Literal

from app.schemas.base import CamelModel


class CrossRunNarrativePattern(CamelModel):
    title: str
    summary: str
    affected_runs: int


class CrossRunNarrativeRecommendation(CamelModel):
    priority: str
    action: str
    expected_impact: str = ""


class PlatformCrossRunNarrative(CamelModel):
    schema_version: Literal["v1"] = "v1"
    schema_key: Literal["platform_cross_run_narrative_v1"] = "platform_cross_run_narrative_v1"
    schema_owner: Literal["backend"] = "backend"
    executive_summary: str
    trend_analysis: str
    critical_patterns: list[CrossRunNarrativePattern]
    strategic_recommendations: list[CrossRunNarrativeRecommendation]
