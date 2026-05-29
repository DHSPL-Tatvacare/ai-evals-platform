"""Read-service ``run_report`` aggregation tests over a live two-channel run."""

from __future__ import annotations

import pytest

from app.constants import SYSTEM_TENANT_ID
from app.services.orchestration.adapters import registered_adapter_instances
from app.services.orchestration.analytics import read_service
from app.services.orchestration.analytics.read_service import WORKFLOW_TENANT_ALL


def _voice_funnel_keys() -> list[str]:
    """Voice adapter funnel stage keys, registry-derived (no vendor literal)."""
    for adapter in registered_adapter_instances():
        if getattr(adapter, "capability", None) == "voice":
            return [s.key for s in adapter.funnel_stages()]
    return []


@pytest.mark.asyncio
async def test_run_report_two_channels_funnel_talktime_and_recipients(
    db_session, seed_orchestration_run
):
    # Voice: one answered (with duration+transcript), one no_answer, one failed.
    # WhatsApp: one delivered+read, one delivered only.
    seeded = await seed_orchestration_run(
        recipients=[
            {
                "recipient_id": "v-ans",
                "channel": "voice",
                "action_type": "bolna_answered",
                "bucket": "positive",
                "voice_duration_sec": 120,
                "voice_transcript": "hello there",
                "attributes": {"name": "Asha", "plan": "gold"},
            },
            {
                "recipient_id": "v-nr",
                "channel": "voice",
                "action_type": "bolna_rnr",
                "bucket": "no_response",
                "voice_duration_sec": 40,
            },
            {
                "recipient_id": "v-fail",
                "channel": "voice",
                "action_type": "bolna_failed",
                "bucket": "failed",
            },
            {
                "recipient_id": "wa-read",
                "channel": "whatsapp",
                "events": [
                    {"action_type": "wa_delivered", "bucket": "reached"},
                    {"action_type": "wa_read", "bucket": "reached"},
                ],
            },
            {
                "recipient_id": "wa-del",
                "channel": "whatsapp",
                "events": [{"action_type": "wa_delivered", "bucket": "reached"}],
            },
        ],
    )

    report = await read_service.run_report(
        db_session,
        run_id=seeded["run_id"],
        tenant_id=SYSTEM_TENANT_ID,
        scope_clause=WORKFLOW_TENANT_ALL(SYSTEM_TENANT_ID),
        recipient_limit=50,
    )
    assert report is not None

    # Head + buckets reuse run_detail bodies.
    assert report.recipients_total == 5
    assert report.buckets.positive == 1
    assert report.buckets.reached == 2
    assert report.buckets.no_response == 1
    assert report.buckets.failed == 1
    assert report.buckets.in_flight == 0
    assert report.duration_seconds is not None and report.duration_seconds >= 0

    # One channel entry per capability present.
    caps = {c.capability for c in report.channels}
    assert caps == {"voice", "messaging"}

    voice = next(c for c in report.channels if c.capability == "voice")
    messaging = next(c for c in report.channels if c.capability == "messaging")

    # Funnel stages: keys mirror the adapter's funnel_stages(); counts are cumulative
    # (weakest stage counts everyone who reached at-or-above it).
    assert [s.key for s in voice.stages] == _voice_funnel_keys()
    voice_counts = {s.key: s.count for s in voice.stages}
    # 3 voice recipients dispatched; 1 positive. Strongest stage = positive count.
    assert voice_counts[voice.stages[-1].key] == 1
    # Weakest stage counts every recipient that reached at-or-above it (>=1 positive).
    assert voice_counts[voice.stages[0].key] >= voice_counts[voice.stages[-1].key]

    # Talk-time: avg/total over answered voice (duration_sec on the answered action response).
    assert messaging.metrics == {}
    assert voice.metrics["totalDurationSec"] == 120
    assert voice.metrics["avgDurationSec"] == 120

    # Recipients: engagement-first (answered/positive first), passthrough attributes,
    # degrade to null when the dataset lacks the column.
    by_id = {r.recipient_id: r for r in report.recipients}
    assert report.recipients_total_count == 5
    assert len(report.recipients) == 5
    assert report.recipients[0].recipient_id == "v-ans"  # positive ranks first

    asha = by_id["v-ans"]
    assert asha.attributes.get("name") == "Asha"
    assert asha.attributes.get("plan") == "gold"

    # A recipient whose dataset attributes are absent degrades to null/empty.
    fail = by_id["v-fail"]
    assert fail.display_name is None
    assert fail.attributes == {}

    # Per-recipient channels are a generic list, never typed voice_*/wa_* fields.
    voice_chan = next(c for c in asha.channels if c.capability == "voice")
    assert voice_chan.outcome_bucket == "positive"
