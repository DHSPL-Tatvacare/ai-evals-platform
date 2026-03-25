# backend/app/services/reports/inside_sales_aggregator.py
"""Aggregation engine for inside sales call evaluations.

Reads dimension keys dynamically from evaluator output_schema.
No hardcoded dimension names.
"""

from __future__ import annotations

import logging
from statistics import mean

from .flag_utils import aggregate_flag, aggregate_outcome_flag

logger = logging.getLogger(__name__)

VERDICT_THRESHOLDS = {"strong": 80, "good": 65, "needsWork": 50}


def _classify_verdict(score: float) -> str:
    if score >= VERDICT_THRESHOLDS["strong"]:
        return "strong"
    if score >= VERDICT_THRESHOLDS["good"]:
        return "good"
    if score >= VERDICT_THRESHOLDS["needsWork"]:
        return "needsWork"
    return "poor"


def _get_eval_output(thread: dict) -> dict | None:
    result = thread.get("result", {})
    evals = result.get("evaluations", [])
    if evals:
        return evals[0].get("output", {})
    return None


def _get_call_metadata(thread: dict) -> dict:
    return thread.get("result", {}).get("call_metadata", {})


class InsideSalesAggregator:
    def __init__(
        self,
        threads: list[dict],
        output_schema: list[dict],
        agent_names: dict[str, str],
    ):
        self.threads = [t for t in threads if t.get("success_status")]
        self.output_schema = output_schema
        self.agent_names = agent_names

        self.dimension_fields = []
        self.compliance_fields = []
        self.overall_score_key = "overall_score"

        for field in output_schema:
            key = field.get("key", "")
            ftype = field.get("type", "")
            if field.get("main_metric"):
                self.overall_score_key = key
            elif ftype == "number" and not field.get("hidden") and not field.get("role"):
                self.dimension_fields.append(field)
            elif ftype == "boolean" and key.startswith("compliance_"):
                self.compliance_fields.append(field)

    def aggregate(self) -> dict:
        outputs = []
        for t in self.threads:
            out = _get_eval_output(t)
            if out:
                outputs.append((t, out))

        return {
            "runSummary": self._run_summary(outputs),
            "dimensionBreakdown": self._dimension_breakdown(outputs),
            "complianceBreakdown": self._compliance_breakdown(outputs),
            "flagStats": self._flag_stats(outputs),
            "agentSlices": self._agent_slices(outputs),
        }

    def _run_summary(self, outputs):
        scores = [out.get(self.overall_score_key, 0) for _, out in outputs]
        avg = mean(scores) if scores else 0

        verdicts = {"strong": 0, "good": 0, "needsWork": 0, "poor": 0}
        for s in scores:
            verdicts[_classify_verdict(s)] += 1

        compliance_violations = 0
        for _, out in outputs:
            for cf in self.compliance_fields:
                if out.get(cf["key"]) is False:
                    compliance_violations += 1
                    break

        total = len(self.threads)
        evaluated = len(outputs)
        pass_count = evaluated - compliance_violations

        return {
            "totalCalls": total,
            "evaluatedCalls": evaluated,
            "avgQaScore": round(avg, 1),
            "verdictDistribution": verdicts,
            "compliancePassRate": round(pass_count / evaluated * 100, 1) if evaluated else 0,
            "complianceViolationCount": compliance_violations,
        }

    def _dimension_breakdown(self, outputs):
        breakdown = {}
        for field in self.dimension_fields:
            key = field["key"]
            values = [out.get(key, 0) for _, out in outputs if out.get(key) is not None]
            if not values:
                continue

            max_possible = field.get("max", 100)
            bucket_size = max_possible / 5
            distribution = [0, 0, 0, 0, 0]
            for v in values:
                idx = min(int(v / bucket_size), 4) if bucket_size > 0 else 0
                distribution[idx] += 1

            breakdown[key] = {
                "label": field.get("label", key),
                "avg": round(mean(values), 1),
                "min": round(min(values), 1),
                "max": round(max(values), 1),
                "maxPossible": max_possible,
                "greenThreshold": field.get("green_threshold", max_possible * 0.8),
                "yellowThreshold": field.get("yellow_threshold", max_possible * 0.5),
                "distribution": distribution,
            }
        return breakdown

    def _compliance_breakdown(self, outputs):
        breakdown = {}
        for field in self.compliance_fields:
            key = field["key"]
            passed = sum(1 for _, out in outputs if out.get(key) is True)
            failed = sum(1 for _, out in outputs if out.get(key) is False)
            breakdown[key] = {
                "label": field.get("label", key),
                "passed": passed,
                "failed": failed,
                "total": passed + failed,
            }
        return breakdown

    def _flag_stats(self, outputs):
        bf_items = [out.get("behavioral_flags", {}) for _, out in outputs]
        of_items = [out.get("outcome_flags", {}) for _, out in outputs]

        # Tension needs special handling for severity
        tension_items = [bf.get("tension_moments", {}) for bf in bf_items]
        tension_relevant = 0
        tension_not_relevant = 0
        severity_counts = {"low": 0, "medium": 0, "high": 0}
        for item in tension_items:
            moments = item.get("moments", "not_relevant")
            if moments == "not_relevant":
                tension_not_relevant += 1
            else:
                tension_relevant += 1
                if isinstance(moments, list):
                    for m in moments:
                        sev = m.get("severity", "low")
                        if sev in severity_counts:
                            severity_counts[sev] += 1

        return {
            "escalation": aggregate_flag([bf.get("escalation", {}) for bf in bf_items]),
            "disagreement": aggregate_flag([bf.get("disagreement", {}) for bf in bf_items]),
            "tension": {
                "relevant": tension_relevant,
                "notRelevant": tension_not_relevant,
                "bySeverity": severity_counts,
            },
            "meetingSetup": aggregate_outcome_flag(
                [of.get("meeting_setup", {}) for of in of_items], attempted_key="occurred",
            ),
            "purchaseMade": aggregate_outcome_flag(
                [of.get("purchase_made", {}) for of in of_items], attempted_key="occurred",
            ),
            "callbackScheduled": aggregate_outcome_flag(
                [of.get("callback_scheduled", {}) for of in of_items], attempted_key="occurred",
            ),
            "crossSell": aggregate_outcome_flag(
                [of.get("cross_sell", {}) for of in of_items],
                attempted_key="attempted", accepted_key="accepted",
            ),
        }

    def _agent_slices(self, outputs):
        agent_groups: dict[str, list[tuple]] = {}
        for thread, out in outputs:
            meta = _get_call_metadata(thread)
            agent_id = meta.get("agent_id", "unknown")
            agent_groups.setdefault(agent_id, []).append((thread, out))

        slices = {}
        for agent_id, agent_outputs in agent_groups.items():
            scores = [out.get(self.overall_score_key, 0) for _, out in agent_outputs]
            verdicts = {"strong": 0, "good": 0, "needsWork": 0, "poor": 0}
            for s in scores:
                verdicts[_classify_verdict(s)] += 1

            dims = {}
            for field in self.dimension_fields:
                key = field["key"]
                values = [out.get(key, 0) for _, out in agent_outputs if out.get(key) is not None]
                dims[key] = {"avg": round(mean(values), 1) if values else 0}

            comp_passed = 0
            comp_failed = 0
            for _, out in agent_outputs:
                has_violation = False
                for cf in self.compliance_fields:
                    if out.get(cf["key"]) is False:
                        has_violation = True
                        break
                if has_violation:
                    comp_failed += 1
                else:
                    comp_passed += 1

            agent_flags = self._flag_stats(agent_outputs)

            slices[agent_id] = {
                "agentName": self.agent_names.get(agent_id, agent_id),
                "callCount": len(agent_outputs),
                "avgQaScore": round(mean(scores), 1) if scores else 0,
                "dimensions": dims,
                "compliance": {"passed": comp_passed, "failed": comp_failed},
                "flags": agent_flags,
                "verdictDistribution": verdicts,
            }
        return slices
