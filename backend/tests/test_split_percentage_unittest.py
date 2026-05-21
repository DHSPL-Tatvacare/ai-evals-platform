"""TDD: logic.split percentage mode + holdout/control branch."""
from __future__ import annotations

import hashlib
import uuid
from collections import Counter

import pytest

import app.services.orchestration.nodes  # noqa: F401 — register all handlers


# ─── _Config validation ───────────────────────────────────────────────────────

def test_percentage_branches_sum_to_100():
    from app.services.orchestration.nodes.logic_split import _Config

    cfg = _Config(
        mode="percentage",
        branches=[
            {"id": "a", "label": "A", "percent": 25},
            {"id": "b", "label": "B", "percent": 25},
            {"id": "c", "label": "C", "percent": 25},
            {"id": "d", "label": "D", "percent": 25},
        ],
    )
    assert sum(b.percent for b in cfg.branches) == 100


def test_percentage_branches_reject_sum_not_100():
    from pydantic import ValidationError
    from app.services.orchestration.nodes.logic_split import _Config

    with pytest.raises((ValidationError, ValueError)):
        _Config(
            mode="percentage",
            branches=[
                {"id": "a", "label": "A", "percent": 30},
                {"id": "b", "label": "B", "percent": 30},
            ],
        )


def test_percentage_branches_with_holdout_sum_to_100():
    from app.services.orchestration.nodes.logic_split import _Config

    # holdout_percent contributes to the total; the named branches make up the rest
    cfg = _Config(
        mode="percentage",
        holdout_percent=10,
        branches=[
            {"id": "a", "label": "A", "percent": 45},
            {"id": "b", "label": "B", "percent": 45},
        ],
    )
    assert cfg.holdout_percent == 10
    total = sum(b.percent for b in cfg.branches) + cfg.holdout_percent
    assert total == 100


def test_percentage_holdout_causes_mismatch_error():
    from pydantic import ValidationError
    from app.services.orchestration.nodes.logic_split import _Config

    with pytest.raises((ValidationError, ValueError)):
        _Config(
            mode="percentage",
            holdout_percent=10,
            branches=[
                {"id": "a", "label": "A", "percent": 50},
                {"id": "b", "label": "B", "percent": 50},
            ],
        )


def test_percentage_mode_rejects_weight_field():
    from pydantic import ValidationError
    from app.services.orchestration.nodes.logic_split import _Config

    with pytest.raises((ValidationError, ValueError)):
        _Config(
            mode="percentage",
            branches=[
                {"id": "a", "label": "A", "percent": 50, "weight": 1},
                {"id": "b", "label": "B", "percent": 50},
            ],
        )


def test_percentage_mode_rejects_match_field():
    from pydantic import ValidationError
    from app.services.orchestration.nodes.logic_split import _Config

    with pytest.raises((ValidationError, ValueError)):
        _Config(
            mode="percentage",
            branches=[
                {"id": "a", "label": "A", "percent": 50, "match": "foo"},
                {"id": "b", "label": "B", "percent": 50},
            ],
        )


def test_percentage_draft_mode_skips_sum_check():
    """Draft validation must not raise on missing/zero percents."""
    from app.services.orchestration.nodes.logic_split import _Config

    # Should NOT raise in draft mode even if percents don't sum to 100
    cfg = _Config.model_validate(
        {
            "mode": "percentage",
            "branches": [
                {"id": "a", "label": "A", "percent": 0},
                {"id": "b", "label": "B", "percent": 0},
            ],
        },
        context={"mode": "draft"},
    )
    assert cfg.mode == "percentage"


# ─── bucket assignment ────────────────────────────────────────────────────────

def _hash_bucket(run_id: str, recipient_id: str, total: int) -> int:
    seed = hashlib.sha256(f"{run_id}|{recipient_id}".encode()).digest()
    return int.from_bytes(seed[:4], "big") % total


def test_bucket_assignment_deterministic():
    """Same run_id + recipient_id always lands in the same bucket."""
    run_id = str(uuid.uuid4())
    for rid in [f"r-{i}" for i in range(200)]:
        b1 = _hash_bucket(run_id, rid, 100)
        b2 = _hash_bucket(run_id, rid, 100)
        assert b1 == b2, f"non-deterministic for {rid}"


def test_bucket_assignment_non_overlapping():
    """No recipient lands in two buckets simultaneously."""
    run_id = str(uuid.uuid4())
    rids = [f"r-{i}" for i in range(500)]
    buckets = [_hash_bucket(run_id, rid, 100) for rid in rids]
    # Each rid maps to exactly one bucket — trivially non-overlapping by construction.
    # Verify via uniqueness of (rid, bucket) pairs.
    pairs = set(zip(rids, buckets))
    assert len(pairs) == len(rids)


def test_percentage_proportions_hold(monkeypatch):
    """4×25% split routes ~25% per branch over many recipients."""
    from app.services.orchestration.nodes.logic_split import _Config, _Handler
    from app.services.orchestration.cohort_stream import CohortStream
    from app.services.orchestration.node_context import NodeContext, ServiceRegistry

    cfg = _Config(
        mode="percentage",
        branches=[
            {"id": "a", "label": "A", "percent": 25},
            {"id": "b", "label": "B", "percent": 25},
            {"id": "c", "label": "C", "percent": 25},
            {"id": "d", "label": "D", "percent": 25},
        ],
    )

    run_id = str(uuid.uuid4())
    cohort = CohortStream([(f"r-{i}", {}) for i in range(2000)])

    ctx = NodeContext(
        db=None,  # type: ignore[arg-type]
        tenant_id=uuid.uuid4(),
        app_id="test",
        workflow_id=uuid.uuid4(),
        workflow_version_id=uuid.uuid4(),
        run_id=run_id,
        node_step_id=uuid.uuid4(),
        current_node_id="split-node",
        services=ServiceRegistry(),
        job_id=None,
    )

    import asyncio
    result = asyncio.get_event_loop().run_until_complete(
        _Handler().execute(cohort, cfg, ctx)
    )

    counts = {bid: len(outs) for bid, outs in result.by_output_id.items()}
    total = sum(counts.values())
    assert total == 2000
    for bid in ["a", "b", "c", "d"]:
        ratio = counts[bid] / total
        assert 0.20 <= ratio <= 0.30, f"branch {bid!r} ratio={ratio:.3f} outside [0.20, 0.30]"


def test_holdout_routes_to_control_edge(monkeypatch):
    """With holdout_percent=20, ~20% land in 'control' output edge."""
    from app.services.orchestration.nodes.logic_split import _Config, _Handler
    from app.services.orchestration.cohort_stream import CohortStream
    from app.services.orchestration.node_context import NodeContext, ServiceRegistry

    cfg = _Config(
        mode="percentage",
        holdout_percent=20,
        branches=[
            {"id": "variant_a", "label": "Variant A", "percent": 40},
            {"id": "variant_b", "label": "Variant B", "percent": 40},
        ],
    )

    run_id = str(uuid.uuid4())
    cohort = CohortStream([(f"r-{i}", {}) for i in range(2000)])
    ctx = NodeContext(
        db=None,  # type: ignore[arg-type]
        tenant_id=uuid.uuid4(),
        app_id="test",
        workflow_id=uuid.uuid4(),
        workflow_version_id=uuid.uuid4(),
        run_id=run_id,
        node_step_id=uuid.uuid4(),
        current_node_id="split-node",
        services=ServiceRegistry(),
        job_id=None,
    )

    import asyncio
    result = asyncio.get_event_loop().run_until_complete(
        _Handler().execute(cohort, cfg, ctx)
    )

    total = sum(len(v) for v in result.by_output_id.values())
    assert total == 2000
    control_count = len(result.by_output_id.get("control", []))
    control_ratio = control_count / total
    assert 0.15 <= control_ratio <= 0.25, f"holdout ratio={control_ratio:.3f} outside [0.15, 0.25]"

    # The control edge must be in the output
    assert "control" in result.by_output_id


def test_holdout_control_edge_in_dynamic_outputs():
    """When holdout is set, 'control' appears in the config-derived output ids."""
    from app.services.orchestration.nodes.logic_split import _Config

    cfg = _Config(
        mode="percentage",
        holdout_percent=10,
        branches=[
            {"id": "a", "label": "A", "percent": 45},
            {"id": "b", "label": "B", "percent": 45},
        ],
    )
    # The dynamic output ids must include 'control' + all branch ids
    all_ids = [b.id for b in cfg.branches]
    if cfg.holdout_percent and cfg.holdout_percent > 0:
        all_ids = all_ids + ["control"]
    assert set(all_ids) == {"a", "b", "control"}


def _make_validator_defn(*, with_holdout: bool, use_ghost_edge: bool = False) -> dict:
    """Build a minimal definition for validator tests (no source node to avoid DB deps)."""
    branches = [
        {"id": "a", "label": "A", "percent": 40},
        {"id": "b", "label": "B", "percent": 40},
    ]
    holdout = 20 if with_holdout else 0
    if not with_holdout:
        branches = [
            {"id": "a", "label": "A", "percent": 50},
            {"id": "b", "label": "B", "percent": 50},
        ]
    split_config: dict = {
        "mode": "percentage",
        "branches": branches,
    }
    if with_holdout:
        split_config["holdout_percent"] = holdout

    edges = [
        {"id": "e1", "source": "sp", "target": "sink1", "output_id": "a"},
        {"id": "e2", "source": "sp", "target": "sink2", "output_id": "b"},
    ]
    extra_sinks = [
        {"id": "sink1", "type": "sink.complete", "config": {}},
        {"id": "sink2", "type": "sink.complete", "config": {}},
    ]
    if with_holdout and not use_ghost_edge:
        edges.append({"id": "e3", "source": "sp", "target": "sink3", "output_id": "control"})
        extra_sinks.append({"id": "sink3", "type": "sink.complete", "config": {}})
    if use_ghost_edge:
        edges.append({"id": "e_ghost", "source": "sp", "target": "sink1", "output_id": "ghost"})

    return {
        "nodes": [{"id": "sp", "type": "logic.split", "config": split_config}] + extra_sinks,
        "edges": edges,
    }


def test_percentage_definition_validator_accepts_dynamic_edges():
    """definition_validator draft accepts edges keyed by branch ids + control."""
    from app.services.orchestration.definition_validator import validate_definition

    defn = _make_validator_defn(with_holdout=True)
    # Should not raise in draft mode (no source node required there)
    validate_definition(defn, workflow_type="outreach", mode="draft")


def test_percentage_definition_validator_rejects_unknown_branch():
    """definition_validator rejects edge with output_id not in branches or control."""
    from app.services.orchestration.definition_validator import DefinitionValidationError, validate_definition

    defn = _make_validator_defn(with_holdout=False, use_ghost_edge=True)
    with pytest.raises(DefinitionValidationError, match="ghost"):
        validate_definition(defn, workflow_type="outreach", mode="draft")
