"""AI narrative generator for custom evaluations report section.

Separate LLM call from main report narrative — custom eval narrative focuses
on evaluator-specific patterns and findings.
"""

import logging

from app.services.evaluators.llm_base import BaseLLMProvider

from .schemas import (
    CustomEvalNarrative,
    CustomEvalNarrativeFinding,
    CustomEvaluationsReport,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a professional AI evaluation analyst. You are reviewing the results \
of custom evaluator runs attached to a batch evaluation of an AI assistant.

Each evaluator was designed to assess specific aspects of the assistant's \
performance across multiple conversation threads. You will receive aggregated \
statistics and text samples from each evaluator.

Your task is to produce a structured analysis highlighting key patterns, \
concerning findings, and notable observations.

Be concise, data-driven, and specific. Reference actual metric values in your findings."""

NARRATIVE_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "overall_assessment": {
            "type": "string",
            "description": "3-5 sentence high-level summary of custom evaluator results.",
        },
        "key_findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "finding": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                    },
                    "affected_count": {"type": "integer"},
                },
                "required": ["finding", "severity", "affected_count"],
            },
            "description": "3-7 key findings from the evaluator results.",
        },
        "notable_patterns": {
            "type": "array",
            "items": {"type": "string"},
            "description": "2-5 notable patterns observed across evaluators.",
        },
    },
    "required": ["overall_assessment", "key_findings", "notable_patterns"],
}


class CustomEvalNarrator:
    """Generates AI narrative for the custom evaluations report section."""

    def __init__(self, provider: BaseLLMProvider):
        self.provider = provider

    async def generate(
        self,
        report: CustomEvaluationsReport,
        text_samples: dict[str, dict[str, list[str]]],
        metadata: dict,
    ) -> CustomEvalNarrative | None:
        """Generate narrative from aggregated custom eval data.

        Args:
            report: aggregated CustomEvaluationsReport (without narrative).
            text_samples: {eval_id: {field_key: [sample_str, ...]}}.
            metadata: run metadata dict for context.

        Returns CustomEvalNarrative or None on failure.
        """
        try:
            prompt = self._build_prompt(report, text_samples, metadata)
            result = await self.provider.generate_json(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                json_schema=NARRATIVE_JSON_SCHEMA,
            )

            return CustomEvalNarrative(
                overall_assessment=result.get("overall_assessment", ""),
                key_findings=[
                    CustomEvalNarrativeFinding(**f)
                    for f in result.get("key_findings", [])
                ],
                notable_patterns=result.get("notable_patterns", []),
            )

        except Exception as e:
            logger.error("Custom eval narrative generation failed: %s", e, exc_info=True)
            return None

    @staticmethod
    def _build_prompt(
        report: CustomEvaluationsReport,
        text_samples: dict[str, dict[str, list[str]]],
        metadata: dict,
    ) -> str:
        """Build user prompt with structured evaluator data."""
        lines = [
            "# Custom Evaluator Results\n",
            f"Run: {metadata.get('run_name') or metadata.get('run_id', 'N/A')}",
            f"App: {metadata.get('app_id', 'N/A')}",
            f"Total threads: {metadata.get('completed_threads', 'N/A')}\n",
        ]

        for section in report.evaluator_sections:
            lines.append(f"## Evaluator: {section.evaluator_name}")
            lines.append(
                f"Completed: {section.completed}/{section.total_threads} "
                f"(error rate: {section.error_rate:.1%})\n"
            )

            for field in section.fields:
                lines.append(f"### Field: {field.label} ({field.field_type})")

                if field.field_type == "number" and field.average is not None:
                    lines.append(f"  Average: {field.average}")
                    if field.threshold_pass_rates:
                        tr = field.threshold_pass_rates
                        lines.append(
                            f"  Pass rates — Green (>={tr.green_threshold}): {tr.green_pct}%, "
                            f"Yellow: {tr.yellow_pct}%, Red: {tr.red_pct}%"
                        )

                elif field.field_type == "boolean":
                    lines.append(
                        f"  Pass rate: {field.pass_rate:.1%} "
                        f"(true: {field.true_count}, false: {field.false_count})"
                    )

                elif field.field_type == "enum" and field.distribution:
                    dist_str = ", ".join(
                        f"{k}: {v}" for k, v in sorted(
                            field.distribution.items(),
                            key=lambda x: x[1],
                            reverse=True,
                        )
                    )
                    lines.append(f"  Distribution: {dist_str}")

                elif field.field_type in ("text", "array"):
                    lines.append(f"  Samples: {field.sample_count}")

                lines.append("")

            # Add text samples for this evaluator
            eval_samples = text_samples.get(section.evaluator_id, {})
            if eval_samples:
                lines.append("### Text/Array Samples")
                for field_key, samples in eval_samples.items():
                    if samples:
                        lines.append(f"  {field_key}:")
                        for i, s in enumerate(samples[:5], 1):
                            lines.append(f"    {i}. {s}")
                lines.append("")

        lines.append(
            "\nProduce your analysis as JSON with: overall_assessment (3-5 sentences), "
            "key_findings (3-7 items with finding, severity, affected_count), "
            "and notable_patterns (2-5 items)."
        )

        return "\n".join(lines)
