"""Canonical single-run narrative contract."""

from __future__ import annotations

from typing import Literal

from app.schemas.base import CamelModel


class RunNarrativeIssue(CamelModel):
    title: str
    area: str
    severity: str
    summary: str


class RunNarrativeRecommendation(CamelModel):
    priority: str
    area: str
    action: str
    rationale: str = ""


class RunNarrativeExemplar(CamelModel):
    item_id: str
    label: str
    analysis: str


class RunNarrativePromptGap(CamelModel):
    gap_type: str
    prompt_section: str
    evaluation_rule: str
    suggested_fix: str


class PlatformRunNarrative(CamelModel):
    schema_version: Literal["v1"] = "v1"
    schema_key: Literal["platform_run_narrative_v1"] = "platform_run_narrative_v1"
    schema_owner: Literal["backend"] = "backend"
    executive_summary: str
    issues: list[RunNarrativeIssue]
    recommendations: list[RunNarrativeRecommendation]
    exemplars: list[RunNarrativeExemplar]
    prompt_gaps: list[RunNarrativePromptGap]
