"""Live-DB tests for the unified evaluation write path (persist_evaluation)."""
from __future__ import annotations

import uuid

import pytest_asyncio
from sqlalchemy import select

from app.constants import SYSTEM_TENANT_ID, SYSTEM_USER_ID
from app.models.eval_run import EvaluationRun
from app.models.evaluation import Evaluation, EvaluationDetail, EvaluationTarget
from app.services.evaluators.output_atoms import (
    DetailAtom,
    EvaluationDraft,
    EvaluatorRef,
    Headline,
    TargetRef,
)
from app.services.evaluators.persistence import persist_evaluation

APP_ID = "inside-sales"


@pytest_asyncio.fixture
async def run(db_session):
    """A persisted EvaluationRun to anchor targets/evaluations."""
    r = EvaluationRun(
        tenant_id=SYSTEM_TENANT_ID, user_id=SYSTEM_USER_ID, app_id=APP_ID, eval_type="batch_thread"
    )
    db_session.add(r)
    await db_session.flush()
    return r


async def _targets(db, run_id):
    rows = (await db.execute(
        select(EvaluationTarget).where(EvaluationTarget.run_id == run_id)
    )).scalars().all()
    return rows


async def _evaluations(db, run_id):
    rows = (await db.execute(
        select(Evaluation).where(Evaluation.run_id == run_id)
    )).scalars().all()
    return rows


async def _details(db, run_id):
    rows = (await db.execute(
        select(EvaluationDetail).where(EvaluationDetail.run_id == run_id)
    )).scalars().all()
    return rows


async def test_persist_dimension_style(db_session, run):
    draft = EvaluationDraft(
        target=TargetRef(key="thread-1", type="chat_thread", source_ref="s3://t1", attributes={"agent": "A"}),
        evaluator=EvaluatorRef(id=uuid.uuid4(), name="rubric", version="1"),
        status="ok",
        headline=Headline(key="overall", score=8.0, max=10.0, verdict="good", reasoning="solid"),
        details=[
            DetailAtom(style="dimension", key="rapport", label="Rapport", score=8, max=10, explanation="warm"),
            DetailAtom(style="dimension", key="overall", label="Overall", score=8, max=10, is_main=True),
        ],
    )
    await persist_evaluation(db_session, run, [draft])

    targets = await _targets(db_session, run.id)
    assert len(targets) == 1
    assert targets[0].target_key == "thread-1"
    assert targets[0].target_type == "chat_thread"
    assert targets[0].tenant_id == SYSTEM_TENANT_ID
    assert targets[0].app_id == APP_ID

    evals = await _evaluations(db_session, run.id)
    assert len(evals) == 1
    assert evals[0].status == "ok"
    assert float(evals[0].headline_score) == 8.0
    assert evals[0].evaluator_ref["name"] == "rubric"

    details = await _details(db_session, run.id)
    assert {d.style for d in details} == {"dimension"}
    assert sum(1 for d in details if d.is_main) == 1


async def test_persist_rule_style(db_session, run):
    draft = EvaluationDraft(
        target=TargetRef(key="thread-2", type="chat_thread"),
        evaluator=EvaluatorRef(name="rule_checker"),
        status="ok",
        details=[
            DetailAtom(style="rule", key="R1", label="No PII", status="PASS", explanation="clean"),
            DetailAtom(style="rule", key="R2", label="Greeting", status="FAIL", explanation="missing"),
            DetailAtom(style="rule", key="R3", status="NA"),
        ],
    )
    await persist_evaluation(db_session, run, [draft])
    details = await _details(db_session, run.id)
    assert {d.status for d in details} == {"PASS", "FAIL", "NA"}
    assert all(d.style == "rule" for d in details)


async def test_persist_comparison_style(db_session, run):
    draft = EvaluationDraft(
        target=TargetRef(key="call-3", type="transcript"),
        evaluator=EvaluatorRef(name="correctness"),
        status="ok",
        headline=Headline(key="overall_accuracy", score=0.9, verdict="likely_incorrect"),
        details=[
            DetailAtom(
                style="comparison", key="dosage", locator="segment:4", severity="critical",
                reference_text="5mg", candidate_text="50mg", explanation="10x error",
            ),
        ],
    )
    await persist_evaluation(db_session, run, [draft])
    details = await _details(db_session, run.id)
    assert len(details) == 1
    d = details[0]
    assert d.style == "comparison"
    assert d.severity == "critical"
    assert d.locator == "segment:4"
    assert d.reference_text == "5mg"
    assert d.candidate_text == "50mg"


async def test_two_evaluators_one_target(db_session, run):
    target = TargetRef(key="thread-9", type="chat_thread")
    d1 = EvaluationDraft(target=target, evaluator=EvaluatorRef(name="rubric"), status="ok",
                         details=[DetailAtom(style="dimension", key="a", score=5, max=10)])
    d2 = EvaluationDraft(target=target, evaluator=EvaluatorRef(name="rules"), status="ok",
                         details=[DetailAtom(style="rule", key="R1", status="PASS")])
    await persist_evaluation(db_session, run, [d1, d2])

    targets = await _targets(db_session, run.id)
    assert len(targets) == 1  # one shared target
    evals = await _evaluations(db_session, run.id)
    assert len(evals) == 2
    assert {e.target_id for e in evals} == {targets[0].id}


async def test_builder_output_persists_end_to_end(db_session, run):
    """thread + transcript builders → persist → DB: proves builder atoms are schema-compatible."""
    from types import SimpleNamespace

    from app.services.evaluators.draft_builders import thread_drafts, transcript_drafts

    rc = SimpleNamespace(rule_id="R1", section="safety", status="VIOLATED", followed=None, evidence="bad")
    correctness = [SimpleNamespace(verdict="HARD FAIL", rule_compliance=[rc])]
    t_drafts = thread_drafts(thread_id="thread-e2e", correctness_results=correctness)
    await persist_evaluation(db_session, run, t_drafts)

    c_drafts = transcript_drafts(
        target_key="call-e2e",
        evaluation={"critique": {"segments": [
            {"category": "dosage", "segmentIndex": 2, "severity": "CRITICAL",
             "originalText": "5mg", "judgeText": "50mg"},
        ]}},
        summary={"overall_accuracy": 0.5},
    )
    await persist_evaluation(db_session, run, c_drafts)

    details = await _details(db_session, run.id)
    by_style = {d.style for d in details}
    assert by_style == {"rule", "comparison"}
    rule_row = next(d for d in details if d.style == "rule")
    assert rule_row.status == "FAIL"
    cmp_row = next(d for d in details if d.style == "comparison")
    assert cmp_row.severity == "critical" and cmp_row.locator == "segment:2"


async def test_idempotent_rerun(db_session, run):
    draft = EvaluationDraft(
        target=TargetRef(key="thread-7", type="chat_thread"),
        evaluator=EvaluatorRef(name="rubric"),
        status="ok",
        details=[DetailAtom(style="dimension", key="a", score=5, max=10),
                 DetailAtom(style="dimension", key="b", score=7, max=10)],
    )
    await persist_evaluation(db_session, run, [draft])
    await persist_evaluation(db_session, run, [draft])  # re-run

    assert len(await _targets(db_session, run.id)) == 1
    assert len(await _evaluations(db_session, run.id)) == 1
    assert len(await _details(db_session, run.id)) == 2
