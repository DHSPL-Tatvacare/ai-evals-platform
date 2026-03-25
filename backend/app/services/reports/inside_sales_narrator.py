# backend/app/services/reports/inside_sales_narrator.py
"""AI narrative generator for inside sales reports."""

import json
import logging

from app.services.evaluators.llm_base import BaseLLMProvider

from .inside_sales_schemas import InsideSalesNarrativeOutput
from .prompts.inside_sales_narrative_prompt import INSIDE_SALES_NARRATIVE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class InsideSalesNarrator:
    def __init__(self, llm: BaseLLMProvider):
        self.llm = llm

    async def generate(self, aggregate_data: dict) -> InsideSalesNarrativeOutput | None:
        try:
            user_prompt = (
                "Generate coaching insights for this inside sales call evaluation batch.\n\n"
                f"```json\n{json.dumps(aggregate_data, indent=2, default=str)}\n```"
            )

            response = await self.llm.generate_json(
                user_prompt,
                system_prompt=INSIDE_SALES_NARRATIVE_SYSTEM_PROMPT,
            )

            if isinstance(response, str):
                response = json.loads(response)

            return InsideSalesNarrativeOutput.model_validate(response)
        except Exception as e:
            logger.warning("Inside sales narrative generation failed: %s", e)
            return None
