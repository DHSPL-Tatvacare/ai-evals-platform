"""Auto-import every node module so @register_node fires at app startup.

Add new node modules here. Order doesn't matter — registry collisions raise.
"""
from app.services.orchestration.nodes import (  # noqa: F401
    source_cohort_query,
    source_event_trigger,
    filter_eligibility,
    filter_consent_gate,
    logic_conditional,
    logic_split,
    logic_wait,
    logic_merge,
    core_webhook_out,
    sink_complete,
)
