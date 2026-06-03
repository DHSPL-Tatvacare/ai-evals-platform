"""Unit tests for the workflow-engagement collapse (most-advanced bucket, cost/duration, connection, lead)."""
import unittest
import uuid
from datetime import datetime, timezone

from app.services.orchestration.analytics.workflow_engagement_populator import WorkflowEngagementPopulator


def _dt(sec):
    return datetime(2026, 6, 3, 12, 0, sec, tzinfo=timezone.utc)


class _Action:
    def __init__(self, action_type, channel, *, outcome_bucket=None, parent_action_id=None,
                 response=None, payload=None, provider_status=None, created_at=None, completed_at=None):
        self.action_type = action_type
        self.channel = channel
        self.outcome_bucket = outcome_bucket
        self.parent_action_id = parent_action_id
        self.response = response
        self.payload = payload or {}
        self.provider_status = provider_status
        self.created_at = created_at or _dt(0)
        self.completed_at = completed_at


class _Run:
    def __init__(self):
        self.id = uuid.uuid4()
        self.tenant_id = uuid.uuid4()
        self.app_id = "inside-sales"
        self.workflow_id = uuid.uuid4()
        self.workflow_version_id = uuid.uuid4()
        self.triggered_by = "manual"
        self.status = "completed"
        self.cohort_size_at_entry = 10
        self.started_at = _dt(0)
        self.completed_at = _dt(30)


class CollapseLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pop = WorkflowEngagementPopulator(db=None)  # __init__ only loads the registry maps

    def _row(self, members, *, capability="voice", recipient_id="r1", node_to_conn=None,
             conn_meta=None, lead_ids=frozenset()):
        return self.pop._build_row(
            run=_Run(), workflow_name="wf", recipient_id=recipient_id, capability=capability,
            members=members, node_to_conn=node_to_conn or {}, conn_meta=conn_meta or {}, lead_ids=lead_ids,
        )

    def test_most_advanced_bucket_wins(self):
        members = [
            (_Action("voice_queued", "voice", parent_action_id=None, created_at=_dt(1)), "n1"),
            (_Action("bolna_rnr", "voice", outcome_bucket="no_response", parent_action_id=uuid.uuid4(), created_at=_dt(2)), "n1"),
            (_Action("bolna_answered", "voice", outcome_bucket="positive", parent_action_id=uuid.uuid4(), created_at=_dt(3)), "n1"),
        ]
        row = self._row(members)
        self.assertEqual(row.outcome_bucket, "positive")
        self.assertEqual(row.attempts, 3)
        self.assertEqual(row.dispatch_attempts, 1)  # one parent_action_id IS NULL
        self.assertTrue(row.dispatched)

    def test_pending_only_resolves_to_in_flight(self):
        members = [(_Action("voice_queued", "voice", outcome_bucket=None, parent_action_id=None), "n1")]
        row = self._row(members)
        self.assertEqual(row.outcome_bucket, "in_flight")
        self.assertTrue(row.dispatched)

    def test_cost_sum_and_cost_rows(self):
        members = [
            (_Action("bolna_answered", "voice", outcome_bucket="positive", response={"total_cost": "0.40"}), "n1"),
            (_Action("bolna_rnr", "voice", outcome_bucket="no_response", response={"total_cost": "0.10"}), "n1"),
            (_Action("voice_queued", "voice", parent_action_id=None, response=None), "n1"),
        ]
        row = self._row(members)
        self.assertEqual(float(row.cost), 0.50)
        self.assertEqual(row.cost_rows, 2)

    def test_duration_counted_for_positive_rows_only(self):
        members = [
            (_Action("bolna_answered", "voice", outcome_bucket="positive", response={"duration_sec": "42"}), "n1"),
            (_Action("bolna_rnr", "voice", outcome_bucket="no_response", response={"duration_sec": "99"}), "n1"),
        ]
        row = self._row(members)
        self.assertEqual(float(row.duration_sec), 42.0)  # the no_response 99 is excluded
        self.assertEqual(row.talk_count, 1)

    def test_connection_resolution_and_unmapped(self):
        conn = str(uuid.uuid4())
        members = [(_Action("voice_queued", "voice", parent_action_id=None), "dispatch-node")]
        row = self._row(members, node_to_conn={"dispatch-node": conn},
                        conn_meta={conn: ("bolna", "My Voice Line")})
        self.assertEqual(str(row.connection_id), conn)
        self.assertEqual(row.provider, "bolna")
        self.assertEqual(row.connection_label, "My Voice Line")

        unmapped = self._row([(_Action("voice_queued", "voice", parent_action_id=None), "n-x")])
        self.assertIsNone(unmapped.connection_id)
        self.assertEqual(unmapped.connection_label, "unmapped")

    def test_lead_id_bridges_only_when_in_dim_lead(self):
        m = [(_Action("voice_queued", "voice", parent_action_id=None), "n1")]
        self.assertEqual(self._row(m, recipient_id="P-pareekshith", lead_ids={"P-pareekshith"}).lead_id, "P-pareekshith")
        self.assertIsNone(self._row(m, recipient_id="r-not-a-lead", lead_ids={"P-pareekshith"}).lead_id)

    def test_contact_and_provider_status_and_timestamps(self):
        members = [
            (_Action("voice_queued", "voice", parent_action_id=None, payload={"contact": "+919876543210"},
                     provider_status="queued", created_at=_dt(1)), "n1"),
            (_Action("bolna_answered", "voice", outcome_bucket="positive", provider_status="completed",
                     created_at=_dt(5), completed_at=_dt(9)), "n1"),
        ]
        row = self._row(members)
        self.assertEqual(row.contact_e164, "+919876543210")
        self.assertEqual(row.provider_status, "completed")  # last by order
        self.assertEqual(row.first_dispatched_at, _dt(1))
        self.assertEqual(row.last_event_at, _dt(9))


if __name__ == "__main__":
    unittest.main()
