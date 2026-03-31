"""Cross-run analytics for inside sales report caches."""

from __future__ import annotations

from app.schemas.base import CamelModel
from app.services.reports.cross_run_aggregator import (
    AggregatedIssue,
    AggregatedRecommendation,
    IssuesAndRecommendations,
)

PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}
PRIORITY_TO_RANK = {"P0": 1, "P1": 2, "P2": 4}


class InsideSalesRunSlice(CamelModel):
    run_id: str
    run_name: str | None
    created_at: str
    avg_qa_score: float
    compliance_pass_rate: float
    evaluated_calls: int
    total_calls: int


class InsideSalesCrossRunStats(CamelModel):
    total_runs: int
    all_runs: int
    total_calls: int
    evaluated_calls: int
    avg_qa_score: float
    avg_compliance_pass_rate: float
    avg_dimension_scores: dict[str, float]


class InsideSalesTrendPoint(CamelModel):
    run_id: str
    run_name: str | None
    created_at: str
    avg_qa_score: float
    compliance_pass_rate: float
    evaluated_calls: int
    dimension_scores: dict[str, float]


class InsideSalesDimensionHeatmapRow(CamelModel):
    key: str
    label: str
    avg_score: float
    max_possible: float
    green_threshold: float
    yellow_threshold: float
    cells: list[float | None]


class InsideSalesDimensionHeatmap(CamelModel):
    runs: list[InsideSalesRunSlice]
    rows: list[InsideSalesDimensionHeatmapRow]


class InsideSalesComplianceHeatmapRow(CamelModel):
    key: str
    label: str
    avg_pass_rate: float
    cells: list[float | None]


class InsideSalesComplianceHeatmap(CamelModel):
    runs: list[InsideSalesRunSlice]
    rows: list[InsideSalesComplianceHeatmapRow]


class InsideSalesFlagRollup(CamelModel):
    label: str
    relevant: int
    not_relevant: int
    present: int = 0
    attempted: int = 0
    accepted: int = 0


class InsideSalesFlagRollups(CamelModel):
    behavioral: dict[str, InsideSalesFlagRollup]
    outcomes: dict[str, InsideSalesFlagRollup]


class InsideSalesCrossRunAnalytics(CamelModel):
    stats: InsideSalesCrossRunStats
    score_trend: list[InsideSalesTrendPoint]
    dimension_heatmap: InsideSalesDimensionHeatmap
    compliance_heatmap: InsideSalesComplianceHeatmap
    flag_rollups: InsideSalesFlagRollups
    issues_and_recommendations: IssuesAndRecommendations


class InsideSalesCrossRunAggregator:
    """Aggregate single-run inside sales report caches into cross-run analytics."""

    def __init__(
        self,
        runs_data: list[tuple[dict, dict]],
        all_runs_count: int,
    ):
        self.runs_data = sorted(runs_data, key=lambda x: x[0].get("created_at", ""))
        self.all_runs_count = all_runs_count

    def aggregate(self) -> InsideSalesCrossRunAnalytics:
        runs = self._build_run_slices()
        return InsideSalesCrossRunAnalytics(
            stats=self._build_stats(runs),
            score_trend=self._build_score_trend(),
            dimension_heatmap=self._build_dimension_heatmap(runs),
            compliance_heatmap=self._build_compliance_heatmap(runs),
            flag_rollups=self._build_flag_rollups(),
            issues_and_recommendations=self._build_issues_and_recommendations(),
        )

    def _build_run_slices(self) -> list[InsideSalesRunSlice]:
        slices: list[InsideSalesRunSlice] = []
        for meta, cache in self.runs_data:
            run_summary = cache.get("runSummary", cache.get("run_summary", {}))
            metadata = cache.get("metadata", {})
            batch_meta = meta.get("batch_metadata") or {}
            slices.append(
                InsideSalesRunSlice(
                    run_id=meta["id"],
                    run_name=batch_meta.get("run_name") or batch_meta.get("name") or metadata.get("runName"),
                    created_at=meta.get("created_at", metadata.get("createdAt", "")),
                    avg_qa_score=run_summary.get("avgQaScore", run_summary.get("avg_qa_score", 0)),
                    compliance_pass_rate=run_summary.get(
                        "compliancePassRate",
                        run_summary.get("compliance_pass_rate", 0),
                    ),
                    evaluated_calls=run_summary.get("evaluatedCalls", run_summary.get("evaluated_calls", 0)),
                    total_calls=run_summary.get("totalCalls", run_summary.get("total_calls", 0)),
                )
            )
        return slices

    def _build_stats(self, runs: list[InsideSalesRunSlice]) -> InsideSalesCrossRunStats:
        total_calls = sum(r.total_calls for r in runs)
        evaluated_calls = sum(r.evaluated_calls for r in runs)
        avg_qa_score = (
            round(sum(r.avg_qa_score for r in runs) / len(runs), 1) if runs else 0
        )
        avg_compliance = (
            round(sum(r.compliance_pass_rate for r in runs) / len(runs), 1) if runs else 0
        )

        dimension_scores: dict[str, list[float]] = {}
        for _meta, cache in self.runs_data:
            for key, dim in cache.get("dimensionBreakdown", cache.get("dimension_breakdown", {})).items():
                dimension_scores.setdefault(key, []).append(dim.get("avg", 0))

        avg_dimension_scores = {
            key: round(sum(values) / len(values), 1)
            for key, values in dimension_scores.items()
            if values
        }

        return InsideSalesCrossRunStats(
            total_runs=len(runs),
            all_runs=self.all_runs_count,
            total_calls=total_calls,
            evaluated_calls=evaluated_calls,
            avg_qa_score=avg_qa_score,
            avg_compliance_pass_rate=avg_compliance,
            avg_dimension_scores=avg_dimension_scores,
        )

    def _build_score_trend(self) -> list[InsideSalesTrendPoint]:
        points: list[InsideSalesTrendPoint] = []
        for meta, cache in self.runs_data:
            run_summary = cache.get("runSummary", cache.get("run_summary", {}))
            metadata = cache.get("metadata", {})
            batch_meta = meta.get("batch_metadata") or {}
            dimension_scores = {
                key: dim.get("avg", 0)
                for key, dim in cache.get("dimensionBreakdown", cache.get("dimension_breakdown", {})).items()
            }
            points.append(
                InsideSalesTrendPoint(
                    run_id=meta["id"],
                    run_name=batch_meta.get("run_name") or batch_meta.get("name") or metadata.get("runName"),
                    created_at=meta.get("created_at", metadata.get("createdAt", "")),
                    avg_qa_score=run_summary.get("avgQaScore", run_summary.get("avg_qa_score", 0)),
                    compliance_pass_rate=run_summary.get(
                        "compliancePassRate",
                        run_summary.get("compliance_pass_rate", 0),
                    ),
                    evaluated_calls=run_summary.get("evaluatedCalls", run_summary.get("evaluated_calls", 0)),
                    dimension_scores=dimension_scores,
                )
            )
        return points

    def _build_dimension_heatmap(
        self,
        runs: list[InsideSalesRunSlice],
    ) -> InsideSalesDimensionHeatmap:
        dimension_maps: list[dict[str, dict]] = []
        all_keys: set[str] = set()

        for _meta, cache in self.runs_data:
            dims = cache.get("dimensionBreakdown", cache.get("dimension_breakdown", {}))
            dimension_maps.append(dims)
            all_keys.update(dims.keys())

        rows: list[InsideSalesDimensionHeatmapRow] = []
        for key in sorted(all_keys):
            cells: list[float | None] = []
            label = key
            max_possible = 100.0
            green_threshold = 80.0
            yellow_threshold = 50.0
            for dims in dimension_maps:
                dim = dims.get(key)
                if dim:
                    label = dim.get("label", key)
                    max_possible = dim.get("maxPossible", dim.get("max_possible", 100))
                    green_threshold = dim.get("greenThreshold", dim.get("green_threshold", max_possible * 0.8))
                    yellow_threshold = dim.get("yellowThreshold", dim.get("yellow_threshold", max_possible * 0.5))
                    cells.append(dim.get("avg", 0))
                else:
                    cells.append(None)
            non_null = [cell for cell in cells if cell is not None]
            rows.append(
                InsideSalesDimensionHeatmapRow(
                    key=key,
                    label=label,
                    avg_score=round(sum(non_null) / len(non_null), 1) if non_null else 0,
                    max_possible=max_possible,
                    green_threshold=green_threshold,
                    yellow_threshold=yellow_threshold,
                    cells=cells,
                )
            )

        rows.sort(key=lambda row: row.avg_score)
        return InsideSalesDimensionHeatmap(runs=runs, rows=rows)

    def _build_compliance_heatmap(
        self,
        runs: list[InsideSalesRunSlice],
    ) -> InsideSalesComplianceHeatmap:
        compliance_maps: list[dict[str, dict]] = []
        all_keys: set[str] = set()

        for _meta, cache in self.runs_data:
            gates = cache.get("complianceBreakdown", cache.get("compliance_breakdown", {}))
            compliance_maps.append(gates)
            all_keys.update(gates.keys())

        rows: list[InsideSalesComplianceHeatmapRow] = []
        for key in sorted(all_keys):
            cells: list[float | None] = []
            label = key
            for gates in compliance_maps:
                gate = gates.get(key)
                if gate:
                    label = gate.get("label", key)
                    total = gate.get("total", 0)
                    passed = gate.get("passed", 0)
                    cells.append(round((passed / total), 3) if total else 1.0)
                else:
                    cells.append(None)
            non_null = [cell for cell in cells if cell is not None]
            rows.append(
                InsideSalesComplianceHeatmapRow(
                    key=key,
                    label=label,
                    avg_pass_rate=round(sum(non_null) / len(non_null), 3) if non_null else 0,
                    cells=cells,
                )
            )

        rows.sort(key=lambda row: row.avg_pass_rate)
        return InsideSalesComplianceHeatmap(runs=runs, rows=rows)

    def _build_flag_rollups(self) -> InsideSalesFlagRollups:
        behavioral: dict[str, InsideSalesFlagRollup] = {}
        outcomes: dict[str, InsideSalesFlagRollup] = {}

        def ensure(
            store: dict[str, InsideSalesFlagRollup],
            key: str,
            label: str,
        ) -> InsideSalesFlagRollup:
            if key not in store:
                store[key] = InsideSalesFlagRollup(label=label, relevant=0, not_relevant=0)
            return store[key]

        for _meta, cache in self.runs_data:
            flag_stats = cache.get("flagStats", cache.get("flag_stats", {}))
            for key, label in (
                ("escalation", "Escalations"),
                ("disagreement", "Disagreements"),
                ("tension", "Tension Moments"),
            ):
                raw = flag_stats.get(key, {})
                item = ensure(behavioral, key, label)
                item.relevant += raw.get("relevant", 0)
                item.not_relevant += raw.get("notRelevant", raw.get("not_relevant", 0))
                item.present += raw.get("present", 0)

            for key, label in (
                ("meetingSetup", "Meeting Setup"),
                ("purchaseMade", "Purchase"),
                ("callbackScheduled", "Callback"),
                ("crossSell", "Cross-sell"),
            ):
                raw = flag_stats.get(key, {})
                item = ensure(outcomes, key, label)
                item.relevant += raw.get("relevant", 0)
                item.not_relevant += raw.get("notRelevant", raw.get("not_relevant", 0))
                item.attempted += raw.get("attempted", 0)
                item.accepted += raw.get("accepted", 0)

        return InsideSalesFlagRollups(behavioral=behavioral, outcomes=outcomes)

    def _build_issues_and_recommendations(self) -> IssuesAndRecommendations:
        issue_groups: dict[str, dict] = {}
        rec_groups: dict[str, dict] = {}
        runs_with_narrative = 0
        runs_without_narrative = 0

        for run_idx, (_meta, cache) in enumerate(self.runs_data):
            narrative = cache.get("narrative")
            run_summary = cache.get("runSummary", cache.get("run_summary", {}))
            affected_calls = run_summary.get("evaluatedCalls", run_summary.get("evaluated_calls", 0))

            if not narrative:
                runs_without_narrative += 1
                continue
            runs_with_narrative += 1

            for insight in narrative.get("dimensionInsights", narrative.get("dimension_insights", [])):
                area = (insight.get("dimension", "Dimension")).strip().lower()
                desc = insight.get("insight", "").strip()
                priority = insight.get("priority", "P2")
                self._accumulate_issue(
                    issue_groups,
                    area=area,
                    desc=desc,
                    affected=affected_calls,
                    run_idx=run_idx,
                    rank=PRIORITY_TO_RANK.get(priority, 4),
                )

            flag_patterns = (narrative.get("flagPatterns", narrative.get("flag_patterns", "")) or "").strip()
            if flag_patterns:
                self._accumulate_issue(
                    issue_groups,
                    area="flag patterns",
                    desc=flag_patterns,
                    affected=affected_calls,
                    run_idx=run_idx,
                    rank=2,
                )

            for alert in narrative.get("complianceAlerts", narrative.get("compliance_alerts", [])):
                if not alert:
                    continue
                self._accumulate_issue(
                    issue_groups,
                    area="compliance",
                    desc=str(alert).strip(),
                    affected=affected_calls,
                    run_idx=run_idx,
                    rank=1,
                )

            for rec in narrative.get("recommendations", []):
                area = "coaching"
                action = rec.get("action", "").strip()
                priority = rec.get("priority", "P2")
                if not action:
                    continue
                if area not in rec_groups:
                    rec_groups[area] = {
                        "actions": [],
                        "action_prefixes": set(),
                        "highest_priority": "P2",
                        "run_indices": set(),
                        "estimated_impacts": [],
                        "impact_prefixes": set(),
                    }
                group = rec_groups[area]
                prefix = action[:80].lower()
                if prefix not in group["action_prefixes"]:
                    group["actions"].append(action)
                    group["action_prefixes"].add(prefix)
                if PRIORITY_ORDER.get(priority, 99) < PRIORITY_ORDER.get(group["highest_priority"], 99):
                    group["highest_priority"] = priority
                group["run_indices"].add(run_idx)

        issues = [
            AggregatedIssue(
                area=area.title(),
                descriptions=group["descriptions"],
                total_affected=group["total_affected"],
                run_count=len(group["run_indices"]),
                worst_rank=group["worst_rank"],
            )
            for area, group in issue_groups.items()
        ]
        issues.sort(key=lambda issue: (issue.worst_rank, -issue.run_count, -issue.total_affected))

        recommendations = [
            AggregatedRecommendation(
                area=area.title(),
                highest_priority=group["highest_priority"],
                actions=group["actions"],
                run_count=len(group["run_indices"]),
                estimated_impacts=group["estimated_impacts"],
            )
            for area, group in rec_groups.items()
        ]
        recommendations.sort(
            key=lambda rec: (PRIORITY_ORDER.get(rec.highest_priority, 99), -rec.run_count)
        )

        return IssuesAndRecommendations(
            issues=issues,
            recommendations=recommendations,
            runs_with_narrative=runs_with_narrative,
            runs_without_narrative=runs_without_narrative,
        )

    @staticmethod
    def _accumulate_issue(
        store: dict[str, dict],
        *,
        area: str,
        desc: str,
        affected: int,
        run_idx: int,
        rank: int,
    ) -> None:
        if area not in store:
            store[area] = {
                "descriptions": [],
                "desc_prefixes": set(),
                "total_affected": 0,
                "run_indices": set(),
                "worst_rank": 99,
            }
        group = store[area]
        prefix = desc[:80].lower()
        if desc and prefix not in group["desc_prefixes"]:
            group["descriptions"].append(desc)
            group["desc_prefixes"].add(prefix)
        group["total_affected"] += affected
        group["run_indices"].add(run_idx)
        group["worst_rank"] = min(group["worst_rank"], rank)


InsideSalesDimensionHeatmap.model_rebuild()
InsideSalesComplianceHeatmap.model_rebuild()
InsideSalesFlagRollups.model_rebuild()
InsideSalesCrossRunAnalytics.model_rebuild()
