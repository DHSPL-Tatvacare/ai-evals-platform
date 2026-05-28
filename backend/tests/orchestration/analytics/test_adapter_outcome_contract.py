from app.services.orchestration.adapters import resolve_adapter
from app.services.orchestration.analytics.outcomes import EngagementBucket


def test_bolna_declares_buckets():
    a = resolve_adapter(capability="voice", vendor="bolna")
    assert a.outcome_bucket("bolna_answered") is EngagementBucket.positive
    assert a.outcome_bucket("bolna_rnr") is EngagementBucket.no_response
    assert a.outcome_bucket("bolna_failed") is EngagementBucket.failed


def test_bolna_funnel_stages_ordered():
    a = resolve_adapter(capability="voice", vendor="bolna")
    assert [s.key for s in a.funnel_stages()] == ["dialed", "connected", "answered", "positive"]


def test_wati_declares_buckets():
    a = resolve_adapter(capability="messaging", vendor="wati")
    assert a.outcome_bucket("wa_replied") is EngagementBucket.positive
    assert a.outcome_bucket("wa_read") is EngagementBucket.reached
    assert a.outcome_bucket("wa_delivered") is EngagementBucket.reached
    assert a.outcome_bucket("wa_failed") is EngagementBucket.failed
