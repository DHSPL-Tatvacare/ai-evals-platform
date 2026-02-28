"""Cross-run AI summary narrator.

Takes aggregated cross-run data, calls LLM, returns structured summary.
Same pattern as narrator.py and custom_evaluations/narrator.py.
"""

import logging

from app.services.evaluators.llm_base import BaseLLMProvider
from app.services.reports.cross_run_aggregator import CrossRunAISummary

logger = logging.getLogger(__name__)

CROSS_RUN_SYSTEM_PROMPT = """\
You are an AI evaluation analyst reviewing performance trends across multiple \
evaluation runs. Your task is to synthesize patterns, identify recurring issues, \
and provide actionable strategic recommendations based on cross-run data.

Be concise and data-driven. Reference specific metrics and trends.
Focus on patterns that repeat across runs, not one-off anomalies.\
"""

CROSS_RUN_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "executive_summary": {
            "type": "string",
            "description": "3-5 sentences on overall health trajectory across runs.",
        },
        "trend_analysis": {
            "type": "string",
            "description": "Analysis of health score and metric trends over time.",
        },
        "critical_patterns": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3-7 recurring failure patterns observed across multiple runs.",
        },
        "strategic_recommendations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3-5 prioritized strategic actions based on cross-run analysis.",
        },
    },
    "required": [
        "executive_summary",
        "trend_analysis",
        "critical_patterns",
        "strategic_recommendations",
    ],
}


def _build_cross_run_user_prompt(
    stats: dict,
    health_trend: list[dict],
    top_issues: list[dict],
    top_recommendations: list[dict],
) -> str:
    parts = [
        "## Cross-Run Analysis Data\n",
        f"**Runs analyzed:** {stats.get('totalRuns', stats.get('total_runs', 0))}",
        f"**Total threads evaluated:** {stats.get('totalThreads', stats.get('total_threads', 0))}",
        f"**Average health score:** {stats.get('avgHealthScore', stats.get('avg_health_score', 0))} "
        f"(Grade: {stats.get('avgGrade', stats.get('avg_grade', 'N/A'))})",
    ]

    # Avg breakdown
    avg_bd = stats.get("avgBreakdown", stats.get("avg_breakdown", {}))
    if avg_bd:
        parts.append("\n### Average Breakdown Scores")
        for key, val in avg_bd.items():
            parts.append(f"- {key}: {val}%")

    # Health trend
    if health_trend:
        parts.append("\n### Health Score Trend (chronological)")
        for pt in health_trend[-20:]:  # Limit to last 20 for prompt size
            name = pt.get("runName", pt.get("run_name", ""))
            score = pt.get("healthScore", pt.get("health_score", 0))
            grade = pt.get("grade", "")
            parts.append(f"- {name or 'Run'}: {score} ({grade})")

    # Top issues
    if top_issues:
        parts.append("\n### Top Recurring Issues (by frequency)")
        for issue in top_issues[:10]:
            area = issue.get("area", "")
            run_count = issue.get("runCount", issue.get("run_count", 0))
            affected = issue.get("totalAffected", issue.get("total_affected", 0))
            descs = issue.get("descriptions", [])
            desc_text = descs[0] if descs else ""
            parts.append(f"- **{area}** (seen in {run_count} runs, {affected} threads): {desc_text}")

    # Top recommendations
    if top_recommendations:
        parts.append("\n### Top Recurring Recommendations")
        for rec in top_recommendations[:10]:
            area = rec.get("area", "")
            priority = rec.get("highestPriority", rec.get("highest_priority", "P2"))
            actions = rec.get("actions", [])
            action_text = actions[0] if actions else ""
            parts.append(f"- [{priority}] **{area}**: {action_text}")

    parts.append(
        "\n\nSynthesize the above data into a structured cross-run analysis. "
        "Output valid JSON matching the required schema."
    )

    return "\n".join(parts)


class CrossRunNarrator:
    """Generates AI summary from aggregated cross-run data."""

    def __init__(self, provider: BaseLLMProvider):
        self.provider = provider

    async def generate(
        self,
        stats: dict,
        health_trend: list[dict],
        top_issues: list[dict],
        top_recommendations: list[dict],
    ) -> CrossRunAISummary | None:
        """Generate cross-run AI summary. Returns None on failure."""
        try:
            user_prompt = _build_cross_run_user_prompt(
                stats=stats,
                health_trend=health_trend,
                top_issues=top_issues,
                top_recommendations=top_recommendations,
            )

            result = await self.provider.generate_json(
                prompt=user_prompt,
                system_prompt=CROSS_RUN_SYSTEM_PROMPT,
                json_schema=CROSS_RUN_JSON_SCHEMA,
            )

            return CrossRunAISummary(
                executive_summary=result.get("executive_summary", ""),
                trend_analysis=result.get("trend_analysis", ""),
                critical_patterns=result.get("critical_patterns", []),
                strategic_recommendations=result.get("strategic_recommendations", []),
            )
        except Exception as e:
            logger.error("Cross-run AI summary generation failed: %s", e, exc_info=True)
            return None
