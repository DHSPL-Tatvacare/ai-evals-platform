from app.services.orchestration.analytics.outcomes import EngagementBucket


def test_buckets_are_mutually_exclusive_terminal_set():
    assert {b.value for b in EngagementBucket} == {"positive", "reached", "no_response", "failed", "in_flight"}


def test_is_terminal_excludes_in_flight():
    assert EngagementBucket.positive.is_terminal()
    assert not EngagementBucket.in_flight.is_terminal()
