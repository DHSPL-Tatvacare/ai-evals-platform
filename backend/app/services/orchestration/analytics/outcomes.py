"""Channel-agnostic engagement outcome vocabulary for orchestration analytics."""
from __future__ import annotations
from enum import Enum


class EngagementBucket(str, Enum):
    positive = "positive"
    reached = "reached"
    no_response = "no_response"
    failed = "failed"
    in_flight = "in_flight"

    def is_terminal(self) -> bool:
        return self is not EngagementBucket.in_flight
