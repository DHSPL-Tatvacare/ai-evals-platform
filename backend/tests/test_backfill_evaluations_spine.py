"""Live-DB tests for the Phase-2 backfill job: legacy rows → unified spine, idempotent + reconciled."""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy import select

from app.constants import SYSTEM_TENANT_ID, SYSTEM_USER_ID
from app.models.eval_run import EvaluationRun, EvaluationRunAdversarialResult, EvaluationRunThreadResult
from app.models.evaluation import Evaluation, EvaluationDetail, EvaluationTarget
from app.services.evaluators.backfill.backfill_evaluations import backfill_evaluations, backfill_run

THREAD_RESULT = {
    "correctness_evaluations": [
        {"verdict": "PASS", "rule_compliance": [
            {"status": "FOLLOWED", "rule_id": "r1", "section": "S", "evidence": "ok", "followed": True},
            {"status": "VIOLATED", "rule_id": "r2", "section": "S", "evidence": "bad", "followed": False},
        ]},
    ],
    "intent_evaluations": [{"is_correct_intent": True}, {"is_correct_intent": False}],
}

ADV_RESULT = {
    "verdict": "PASS", "goal_achieved": True, "transcript": [],
    "test_case": {"difficulty": "EASY", "goal_flow": ["meal_logged"]},
    "rule_compliance": [{"status": "FOLLOWED", "rule_id": "ar1", "section": "Safety", "followed": True}],
}


async def _count(db, model, run_id):
    return len((await db.execute(select(model).where(model.run_id == run_id))).scalars().all())


@pytest_asyncio.fixture
async def thread_run(db_session):
    run = EvaluationRun(tenant_id=SYSTEM_TENANT_ID, user_id=SYSTEM_USER_ID, app_id="kaira-bot",
                        eval_type="batch_thread", status="completed")
    db_session.add(run)
    await db_session.flush()
    db_session.add(EvaluationRunThreadResult(run_id=run.id, thread_id="thrd-A", result=THREAD_RESULT))
    db_session.add(EvaluationRunThreadResult(run_id=run.id, thread_id="thrd-B", result=THREAD_RESULT))
    await db_session.flush()
    return run


async def test_backfill_creates_spine(db_session, thread_run):
    summary = await backfill_run(db_session, thread_run)
    assert summary["evaluations"] == 4  # 2 threads × (correctness + intent)
    assert summary["targets"] == 2

    targets = await _count(db_session, EvaluationTarget, thread_run.id)
    evals = await _count(db_session, Evaluation, thread_run.id)
    details = await _count(db_session, EvaluationDetail, thread_run.id)
    assert targets == 2
    assert evals == 4
    # per thread: correctness → 2 rule atoms, intent → 1 dimension atom = 3; ×2 threads = 6
    assert details == 6


async def test_reconciliation_every_thread_has_evaluation(db_session, thread_run):
    await backfill_run(db_session, thread_run)
    thread_keys = {tr.thread_id for tr in (await db_session.execute(
        select(EvaluationRunThreadResult).where(EvaluationRunThreadResult.run_id == thread_run.id)
    )).scalars().all()}
    target_keys = {t.target_key for t in (await db_session.execute(
        select(EvaluationTarget).where(EvaluationTarget.run_id == thread_run.id)
    )).scalars().all()}
    assert thread_keys == target_keys  # every thread_result reconciled to a target
    # zero orphan details
    orphans = (await db_session.execute(
        select(EvaluationDetail).where(
            EvaluationDetail.run_id == thread_run.id,
            EvaluationDetail.evaluation_id.notin_(select(Evaluation.id)),
        )
    )).scalars().all()
    assert orphans == []


async def test_backfill_idempotent(db_session, thread_run):
    await backfill_run(db_session, thread_run)
    await db_session.commit()
    first = (await _count(db_session, Evaluation, thread_run.id),
             await _count(db_session, EvaluationDetail, thread_run.id))
    await backfill_run(db_session, thread_run)  # re-run
    await db_session.commit()
    second = (await _count(db_session, Evaluation, thread_run.id),
              await _count(db_session, EvaluationDetail, thread_run.id))
    assert first == second  # re-run inserts net-zero


async def test_backfill_adversarial_targets(db_session):
    run = EvaluationRun(tenant_id=SYSTEM_TENANT_ID, user_id=SYSTEM_USER_ID, app_id="kaira-bot",
                        eval_type="batch_adversarial", status="completed")
    db_session.add(run)
    await db_session.flush()
    db_session.add(EvaluationRunAdversarialResult(run_id=run.id, verdict="PASS", result=ADV_RESULT))
    db_session.add(EvaluationRunAdversarialResult(run_id=run.id, verdict="PASS", result=ADV_RESULT))
    await db_session.flush()

    summary = await backfill_run(db_session, run)
    assert summary["targets"] == 2  # one target per adversarial row (keyed by row id)
    assert summary["evaluations"] == 2


async def test_backfill_evaluations_filters_by_run_ids(db_session, thread_run):
    totals = await backfill_evaluations(db_session, run_ids=[thread_run.id])
    assert totals["runs"] == 1
    assert totals["evaluations"] == 4
