# backend/app/services/reports/inside_sales_report_service.py
"""Report service for inside sales evaluations.

Extends BaseReportService with inside-sales-specific aggregation and narration.
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import load_only

from app.models.eval_run import EvalRun
from app.models.evaluator import Evaluator
from app.models.external_agent import ExternalAgent

from .base_report_service import BaseReportService
from .inside_sales_aggregator import InsideSalesAggregator
from .inside_sales_narrator import InsideSalesNarrator
from .inside_sales_schemas import (
    InsideSalesReportMetadata,
    InsideSalesReportPayload,
)

logger = logging.getLogger(__name__)


class InsideSalesReportService(BaseReportService):
    payload_model = InsideSalesReportPayload

    async def _load_source_data(self, run_id: str) -> dict[str, list[dict]]:
        threads = await self._load_threads(run_id)
        return {
            "threads": [
                {
                    "thread_id": t.thread_id,
                    "result": t.result,
                    "success_status": t.success_status,
                }
                for t in threads
            ],
        }

    async def _build_payload(
        self,
        run: EvalRun,
        source_data: dict[str, list[dict]],
        llm_provider: str | None = None,
        llm_model: str | None = None,
    ) -> InsideSalesReportPayload:
        thread_dicts = source_data["threads"]

        output_schema = await self._load_evaluator_schema(run, thread_dicts)
        agent_names = await self._load_agent_names(thread_dicts)

        aggregator = InsideSalesAggregator(thread_dicts, output_schema, agent_names)
        aggregate_data = aggregator.aggregate()

        batch_meta = run.batch_metadata or {}
        metadata = InsideSalesReportMetadata(
            run_id=str(run.id),
            run_name=batch_meta.get("name"),
            app_id=run.app_id,
            eval_type=run.eval_type,
            created_at=run.created_at.isoformat() if run.created_at else "",
            llm_provider=run.llm_provider,
            llm_model=run.llm_model,
            total_calls=aggregate_data["runSummary"]["totalCalls"],
            evaluated_calls=aggregate_data["runSummary"]["evaluatedCalls"],
            duration_ms=run.duration_ms,
        )

        narrative = None
        narrative_model = None
        try:
            llm, model_name = await self._create_llm_provider(
                run, "inside_sales_narrative", llm_provider, llm_model,
            )
            if llm:
                narrator = InsideSalesNarrator(llm)
                narrative = await narrator.generate(aggregate_data)
                narrative_model = model_name
        except Exception as e:
            logger.warning("Inside sales narrative skipped: %s", e)

        metadata.narrative_model = narrative_model

        payload = InsideSalesReportPayload(
            metadata=metadata,
            run_summary=aggregate_data["runSummary"],
            dimension_breakdown=aggregate_data["dimensionBreakdown"],
            compliance_breakdown=aggregate_data["complianceBreakdown"],
            flag_stats=aggregate_data["flagStats"],
            agent_slices=aggregate_data["agentSlices"],
            narrative=narrative,
        )
        return payload

    async def _load_evaluator_schema(self, run: EvalRun, threads: list[dict] | None = None) -> list[dict]:
        """Load evaluator output_schema for dimension discovery.

        Tries three sources: run.summary.custom_evaluations, run.config.evaluator_id,
        then falls back to the evaluator_id from the first thread evaluation result.
        """
        summary = run.summary or {}
        evaluator_id = None

        custom_evals = summary.get("custom_evaluations", {})
        if custom_evals:
            evaluator_id = next(iter(custom_evals.keys()), None)

        if not evaluator_id:
            config = run.config or {}
            evaluator_id = config.get("evaluator_id")

        # Fallback: read from first thread evaluation result
        if not evaluator_id and threads:
            for t in threads:
                evals = t.get("result", {}).get("evaluations", [])
                if evals and evals[0].get("evaluator_id"):
                    evaluator_id = evals[0]["evaluator_id"]
                    break

        if not evaluator_id:
            logger.warning("No evaluator_id found for run %s, using empty schema", run.id)
            return []

        try:
            result = await self.db.execute(
                select(Evaluator).where(Evaluator.id == UUID(evaluator_id))
                .options(load_only(Evaluator.output_schema))
            )
            evaluator = result.scalar_one_or_none()
            return evaluator.output_schema or [] if evaluator else []
        except Exception as e:
            logger.warning("Failed to load evaluator schema: %s", e)
            return []

    async def _load_agent_names(self, threads: list[dict]) -> dict[str, str]:
        agent_ids = set()
        for t in threads:
            meta = t.get("result", {}).get("call_metadata", {})
            aid = meta.get("agent_id")
            if aid:
                agent_ids.add(aid)

        if not agent_ids:
            return {}

        try:
            uuids = [UUID(aid) for aid in agent_ids]
            result = await self.db.execute(
                select(ExternalAgent).where(
                    ExternalAgent.id.in_(uuids),
                    ExternalAgent.tenant_id == self.tenant_id,
                )
                .options(load_only(ExternalAgent.id, ExternalAgent.name))
            )
            return {str(a.id): a.name for a in result.scalars().all()}
        except Exception as e:
            logger.warning("Failed to load agent names: %s", e)
            names = {}
            for t in threads:
                meta = t.get("result", {}).get("call_metadata", {})
                aid = meta.get("agent_id")
                if aid and aid not in names:
                    names[aid] = meta.get("agent", aid)
            return names
