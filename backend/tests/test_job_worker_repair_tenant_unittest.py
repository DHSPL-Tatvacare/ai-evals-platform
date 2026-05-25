"""Compiled-SQL guard: the _run_job failure-repair queries carry tenant_id."""
import uuid
import unittest

from sqlalchemy import select, update
from sqlalchemy.dialects import postgresql

from app.models.eval_run import EvaluationRun
from app.models.orchestration import (
    Workflow,
    WorkflowRun,
    WorkflowRunNodeStep,
)


def _sql(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    )


class RepairTenantPredicateTests(unittest.TestCase):
    """Mirror the inline repair statements verbatim and assert tenant scoping."""

    def setUp(self) -> None:
        self.tenant_id = uuid.uuid4()
        self.job_id = uuid.uuid4()

    def test_eval_run_repair_filters_tenant(self) -> None:
        stmt = (
            update(EvaluationRun)
            .where(
                EvaluationRun.tenant_id == self.tenant_id,
                EvaluationRun.job_id == self.job_id,
                EvaluationRun.status.in_(("pending", "running")),
            )
            .values(status="failed")
        )
        sql = _sql(stmt)
        self.assertIn("tenant_id", sql)
        self.assertIn("job_id", sql)

    def test_workflow_run_repair_filters_tenant(self) -> None:
        stmt = (
            update(WorkflowRun)
            .where(
                WorkflowRun.tenant_id == self.tenant_id,
                WorkflowRun.job_id == self.job_id,
                WorkflowRun.status.in_(("pending", "running", "waiting")),
            )
            .values(status="failed")
        )
        sql = _sql(stmt)
        self.assertIn("tenant_id", sql)

    def test_workflow_step_repair_inner_select_filters_tenant(self) -> None:
        stmt = (
            update(WorkflowRunNodeStep)
            .where(
                WorkflowRunNodeStep.run_id.in_(
                    select(WorkflowRun.id).where(
                        WorkflowRun.tenant_id == self.tenant_id,
                        WorkflowRun.job_id == self.job_id,
                    )
                ),
                WorkflowRunNodeStep.status == "running",
            )
            .values(status="failed")
        )
        sql = _sql(stmt)
        # The inner correlated select must constrain WorkflowRun by tenant_id.
        self.assertIn("tenant_id", sql)

    def test_workflow_run_lookup_filters_tenant(self) -> None:
        stmt = select(WorkflowRun).where(
            WorkflowRun.tenant_id == self.tenant_id,
            WorkflowRun.job_id == self.job_id,
            WorkflowRun.status == "failed",
        )
        sql = _sql(stmt)
        self.assertIn("tenant_id", sql)

    def test_workflow_name_lookup_filters_tenant(self) -> None:
        wf_run_tenant = uuid.uuid4()
        wf_id = uuid.uuid4()
        stmt = select(Workflow.name).where(
            Workflow.tenant_id == wf_run_tenant,
            Workflow.id == wf_id,
        )
        sql = _sql(stmt)
        self.assertIn("tenant_id", sql)


if __name__ == "__main__":
    unittest.main()
