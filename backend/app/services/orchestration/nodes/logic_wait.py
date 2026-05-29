"""logic.wait — suspend recipients until time and / or event conditions release them."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ValidationInfo, field_validator, model_validator

from app.services.orchestration._config_strictness import strict_node_config_dict
from app.services.orchestration.node_protocol import NodeResult
from app.services.orchestration.node_registry import register_node
from app.services.orchestration.predicate_contract import parse as parse_predicate


WaitMode = Literal["duration", "until_datetime", "event", "event_or_timeout"]
DurationUnit = Literal["minutes", "hours", "days"]


def _duration_timedelta(value: float, unit: DurationUnit) -> timedelta:
    """Convert a (value, unit) pair to a timedelta."""
    if unit == "minutes":
        return timedelta(minutes=value)
    if unit == "hours":
        return timedelta(hours=value)
    return timedelta(days=value)


class _EventCorrelation(BaseModel):
    """How an inbound event row identifies the parked recipient.

    ``recipient_id_field`` is the JSON path inside the event payload whose
    value matches a parked recipient's ``recipient_id``. Future commits will
    extend this with provider-specific correlation (e.g. ``wati_message_id``
    -> action row -> recipient).
    """
    model_config = strict_node_config_dict()

    recipient_id_field: str


class _Config(BaseModel):
    """Flat union — only the fields valid for the chosen ``mode`` are required."""
    model_config = strict_node_config_dict()

    mode: WaitMode = "duration"

    # New canonical fields for duration mode.
    duration_value: Optional[float] = None
    duration_unit: Optional[DurationUnit] = None
    # Legacy field kept for back-compat reads; coerced into value+unit by the before-validator.
    duration_hours: Optional[float] = None

    until_datetime: Optional[datetime] = None

    event_name: Optional[str] = None
    correlation: Optional[_EventCorrelation] = None
    event_match: Optional[dict[str, Any]] = None
    timeout_hours: Optional[float] = None

    @field_validator("event_match")
    @classmethod
    def _validate_event_match(
        cls,
        value: Optional[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        if value is None:
            return value
        parse_predicate(value)
        return value

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy(cls, raw: Any, info: ValidationInfo) -> Any:
        if not isinstance(raw, dict):
            return raw
        raw = dict(raw)
        # Editor mode-switches can leave a blank optional field behind; drop
        # empty strings so a stray "" never fails the strict datetime / float
        # parse and blocks publish.
        for key in (
            "until_datetime",
            "duration_value",
            "duration_hours",
            "timeout_hours",
            "event_name",
        ):
            if isinstance(raw.get(key), str) and raw[key].strip() == "":
                raw[key] = None
        # Coerce legacy duration_hours → duration_value + duration_unit.
        if raw.get("duration_hours") is not None and raw.get("duration_value") is None:
            raw["duration_value"] = raw["duration_hours"]
            raw["duration_unit"] = raw.get("duration_unit") or "hours"
        if "mode" in raw:
            return raw
        if raw.get("duration_hours") is not None or raw.get("duration_value") is not None:
            return {**raw, "mode": "duration"}
        if raw.get("until_datetime") is not None:
            return {**raw, "mode": "until_datetime"}
        # Draft mode tolerates an in-progress wait node with no mode picked yet.
        if info.context and info.context.get("mode") == "draft":
            return raw
        raise ValueError(
            "logic.wait config requires 'mode' (or legacy "
            "'duration_hours' / 'until_datetime' for back-compat)"
        )

    @model_validator(mode="after")
    def _check_mode_fields(self, info: ValidationInfo) -> "_Config":
        if info.context and info.context.get("mode") == "draft":
            return self
        if self.mode == "duration":
            if self.duration_value is None and self.duration_hours is None:
                raise ValueError(
                    "'duration_value' (or legacy 'duration_hours') required when mode='duration'"
                )
            # Sync duration_hours for callers that still read it.
            if self.duration_value is not None and self.duration_unit == "hours":
                object.__setattr__(self, "duration_hours", self.duration_value)
        elif self.mode == "until_datetime":
            if self.until_datetime is None:
                raise ValueError("'until_datetime' required when mode='until_datetime'")
        elif self.mode == "event":
            if not self.event_name:
                raise ValueError("'event_name' required when mode='event'")
            if self.correlation is None:
                raise ValueError("'correlation' required when mode='event'")
        elif self.mode == "event_or_timeout":
            if not self.event_name:
                raise ValueError("'event_name' required when mode='event_or_timeout'")
            if self.correlation is None:
                raise ValueError("'correlation' required when mode='event_or_timeout'")
            if self.timeout_hours is None:
                raise ValueError("'timeout_hours' required when mode='event_or_timeout'")
        return self


@register_node(workflow_type="*", node_type="logic.wait")
class _Handler:
    node_type = "logic.wait"
    config_schema = _Config
    # Validator picks the actual subset per config; this is the union for
    # registry-level introspection and back-compat rendering.
    output_edges = ["wakeup", "event", "timeout"]
    category = "logic"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        wakeup_at: Optional[datetime] = None
        if config.mode == "duration":
            value = config.duration_value if config.duration_value is not None else config.duration_hours
            unit: DurationUnit = config.duration_unit if config.duration_unit is not None else "hours"
            assert value is not None
            wakeup_at = datetime.now(timezone.utc) + _duration_timedelta(value, unit)
        elif config.mode == "until_datetime":
            assert config.until_datetime is not None
            wakeup_at = config.until_datetime
            if wakeup_at.tzinfo is None:
                wakeup_at = wakeup_at.replace(tzinfo=timezone.utc)
        elif config.mode == "event_or_timeout":
            assert config.timeout_hours is not None
            wakeup_at = datetime.now(timezone.utc) + timedelta(hours=config.timeout_hours)
        # mode='event' parks indefinitely until the event-resume runtime ships;
        # ``wakeup_at`` stays None so the time-based resume poller never picks
        # the recipient up.

        # Lazy import: keeps the node module light when nothing's waiting.
        from app.services.orchestration.dispatch.resume_enqueue import (
            enqueue_resume_for_recipient,
        )

        count = 0
        async for rid, _ in input_cohort:
            await ctx.set_recipient_state(rid, status="waiting", wakeup_at=wakeup_at)
            # When a wakeup time is known, schedule a delayed run-workflow
            # job at exactly that instant. Replaces the every-minute
            # resume-waiting-cohorts cron — the worker picks it up at ±~1s
            # of ``wakeup_at`` instead of ±60s. Mode='event' (no wakeup_at)
            # parks indefinitely; the webhook-driven resume path enqueues
            # the run-workflow inline when the event lands.
            if wakeup_at is not None:
                wakeup_token = str(int(wakeup_at.timestamp()))
                await enqueue_resume_for_recipient(
                    ctx.db,
                    run_id=ctx.run_id,
                    recipient_id=rid,
                    available_at=wakeup_at,
                    reason=f"wakeup:{wakeup_token}",
                )
            count += 1
        summary: dict[str, Any] = {"suspended_count": count, "mode": config.mode}
        if wakeup_at is not None:
            summary["wakeup_at"] = wakeup_at.isoformat()
        return NodeResult(suspended=True, summary=summary)


def expected_output_ids_for_config(config_dict: dict[str, Any]) -> list[str]:
    """Return the ``output_id`` set the validator should expect for a wait config.

    Used by the definition validator to enforce that the persisted edges
    match the wait mode (rule §7.14 in Phase 11):

      duration / until_datetime -> {'wakeup'}
      event                     -> {'event'}
      event_or_timeout          -> {'event', 'timeout'}

    Legacy configs without ``mode`` map to the duration / until_datetime
    case (``wakeup``).
    """
    mode = config_dict.get("mode")
    if mode in (None, "duration", "until_datetime"):
        return ["wakeup"]
    if mode == "event":
        return ["event"]
    if mode == "event_or_timeout":
        return ["event", "timeout"]
    raise ValueError(f"unknown wait mode: {mode!r}")
