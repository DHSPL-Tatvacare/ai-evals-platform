"""Normalizer migrations for the dispatch / mutation contract."""
from __future__ import annotations

import app.services.orchestration.nodes  # noqa: F401 — register handlers
from app.services.orchestration.definition_normalizer import normalize_definition
from app.services.orchestration.definition_validator import validate_definition


def _node(node_id: str, node_type: str, **config) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "position": {"x": 0, "y": 0},
        "config": dict(config),
    }


def _edge(eid: str, source: str, target: str, output_id: str = "default") -> dict:
    return {"id": eid, "source": source, "target": target, "output_id": output_id}


def test_core_webhook_failed_edge_becomes_exhausted():
    """The retry-capable ``core.webhook_out`` node rewrites legacy ``failed`` to ``exhausted``."""
    defn = {
        "nodes": [
            _node("src", "source.event_trigger"),
            _node("wh", "core.webhook_out", url="x", body={}),
            _node("sink", "sink.complete"),
        ],
        "edges": [
            _edge("e1", "src", "wh"),
            _edge("e2", "wh", "sink", output_id="failed"),
        ],
    }
    canon = normalize_definition(defn)
    by_id = {e["id"]: e for e in canon["edges"]}
    assert by_id["e2"]["output_id"] == "exhausted"


def test_webhook_body_template_migrates_to_structured_body():
    defn = {
        "nodes": [
            _node(
                "wh", "core.webhook_out",
                url="https://x", method="POST",
                body_template='{"name": "{{first_name}}", "static": "v"}',
            ),
        ],
        "edges": [],
    }
    canon = normalize_definition(defn)
    cfg = canon["nodes"][0]["config"]
    assert "body_template" not in cfg
    assert cfg["body"] == {"name": {"$payload": "first_name"}, "static": "v"}


def test_webhook_existing_body_takes_priority_over_legacy_template():
    defn = {
        "nodes": [
            _node(
                "wh", "core.webhook_out",
                url="x",
                body={"name": {"$payload": "first_name"}},
                body_template='{"static": "ignored"}',
            ),
        ],
        "edges": [],
    }
    canon = normalize_definition(defn)
    cfg = canon["nodes"][0]["config"]
    assert "body_template" not in cfg
    assert cfg["body"] == {"name": {"$payload": "first_name"}}


def test_conditional_legacy_predicate_migrates_to_branches():
    """Legacy ``{predicate}`` conditional coerces to a single-branch ``{branches}`` shape."""
    predicate = {"field": "tier", "op": "eq", "value": "vip"}
    defn = {
        "nodes": [
            _node("cond", "logic.conditional", predicate=predicate),
        ],
        "edges": [],
    }
    canon = normalize_definition(defn)
    cfg = canon["nodes"][0]["config"]
    assert "predicate" not in cfg
    assert isinstance(cfg["branches"], list) and len(cfg["branches"]) == 1
    branch = cfg["branches"][0]
    assert branch["predicate"] == predicate
    assert branch["id"]
    assert branch["label"]


def test_conditional_legacy_true_false_edges_rewrite():
    """Old true/false outputs map to the new branch id (true) and the implicit default (false)."""
    predicate = {"field": "tier", "op": "eq", "value": "vip"}
    defn = {
        "nodes": [
            _node("src", "source.event_trigger"),
            _node("cond", "logic.conditional", predicate=predicate),
            _node("matched", "sink.complete"),
            _node("unmatched", "sink.complete"),
        ],
        "edges": [
            _edge("e_in", "src", "cond"),
            _edge("e_t", "cond", "matched", output_id="true"),
            _edge("e_f", "cond", "unmatched", output_id="false"),
        ],
    }
    canon = normalize_definition(defn)
    branch_id = canon["nodes"][1]["config"]["branches"][0]["id"]
    by_id = {e["id"]: e for e in canon["edges"]}
    assert by_id["e_t"]["output_id"] == branch_id
    assert by_id["e_f"]["output_id"] == "default"


def test_conditional_already_branches_left_alone():
    """A canonical conditional config is not rewritten."""
    branches = [{"id": "vip", "label": "VIP", "predicate": {"field": "t", "op": "eq", "value": "v"}}]
    defn = {"nodes": [_node("cond", "logic.conditional", branches=branches)], "edges": []}
    canon = normalize_definition(defn)
    assert canon["nodes"][0]["config"]["branches"] == branches
    assert "predicate" not in canon["nodes"][0]["config"]


def test_conditional_legacy_predicate_normalizes_then_passes_publish():
    """A legacy ``{predicate}`` conditional normalizes and publishes cleanly."""
    predicate = {"field": "tier", "op": "eq", "value": "vip"}
    defn = {
        "nodes": [
            {"id": "src", "type": "source.event_trigger", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "cond", "type": "logic.conditional", "position": {"x": 0, "y": 100}, "config": {"predicate": predicate}},
            {"id": "matched", "type": "sink.complete", "position": {"x": 0, "y": 200}, "config": {}},
            {"id": "unmatched", "type": "sink.complete", "position": {"x": 200, "y": 200}, "config": {}},
        ],
        "edges": [
            _edge("e_in", "src", "cond"),
            _edge("e_t", "cond", "matched", output_id="true"),
            _edge("e_f", "cond", "unmatched", output_id="false"),
        ],
        "canvas": {},
    }
    canon = normalize_definition(defn)
    validate_definition(canon, workflow_type="crm", mode="publish")


def test_normalizer_idempotent_on_canonical_definition():
    defn = {
        "nodes": [
            _node("src", "source.event_trigger"),
            _node("wh", "core.webhook_out", connection_id="c", url="https://x", body={}),
            _node("sink", "sink.complete"),
        ],
        "edges": [
            _edge("e1", "src", "wh"),
            _edge("e2", "wh", "sink", output_id="success"),
            _edge("e3", "wh", "sink", output_id="exhausted"),
        ],
    }
    once = normalize_definition(defn)
    twice = normalize_definition(once)
    assert once == twice
