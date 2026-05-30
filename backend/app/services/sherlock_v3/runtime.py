"""Sherlock v3 runtime — one-turn execution that emits typed Parts via PartEmitter."""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from agents import Runner

from app.auth.context import AuthContext
from app.services.orchestration_authoring.builder_snapshot import BuilderSnapshot
from app.services.orchestration_authoring.canvas_patch import (
    CANVAS_PATCH_CONTRACT_ID,
    CanvasPatch,
)
from app.services.sherlock_v3.azure_client import get_sherlock_azure_client
from app.services.sherlock_v3.contracts import (
    AssistantTextPart,
    CanvasPatchPart,
    CompactionPart,
    ErrorPart,
    ReasoningPart,
    SpecialistBrief,
    SpecialistScope,
    StepFinishPart,
    StepStartPart,
    SubtaskPart,
    SubtaskStateCompleted,
    SubtaskStateError,
    SubtaskStateRunning,
    UserMessagePart,
    new_part_id,
)
from app.services.sherlock_v3.emitter import PartEmitter
from app.services.sherlock_v3.subtask_result import project_specialist_output
from app.services.sherlock_v3.limits import MAX_SPECIALIST_ATTEMPTS
from app.services.sherlock_v3.grounding import (
    GroundingContext,
    VerifiedExampleRef,
)
from app.services.sherlock_v3.supervisor import build_supervisor
from app.services.sherlock_v3.compaction import CONTEXT_COMPACT_THRESHOLD_TOKENS

logger = logging.getLogger(__name__)


@dataclass
class SherlockTurnContext:
    """Per-turn handles passed to the SDK as ``RunContextWrapper.context``."""

    tenant_id: uuid.UUID
    user_id: uuid.UUID
    app_id: str
    chat_session_id: uuid.UUID
    turn_id: uuid.UUID
    auth: AuthContext
    emitter: PartEmitter | None = None
    previous_response_id: str | None = None
    streamed_text_parts: list[str] = field(default_factory=list)
    scratch: dict[str, Any] = field(default_factory=dict)
    builder_context: BuilderSnapshot | None = None


_STALE_PREVIOUS_RESPONSE_ID_MARKERS = (
    'previous_response_not_found',
    'previous_response was not found',
    'previous response not found',
)


def _is_stale_previous_response_id(exc: BaseException) -> bool:
    raw = repr(exc).lower()
    return any(marker in raw for marker in _STALE_PREVIOUS_RESPONSE_ID_MARKERS)


@dataclass
class TurnResult:
    """Returned by run_turn — usage + chain head for the caller's finalization."""

    status: str
    usage: dict[str, Any]
    last_response_id: str | None
    error: str | None = None


async def _compute_grounding(
    app_id: str,
    user_message: str,
    *,
    tenant_id: uuid.UUID,
) -> GroundingContext | None:
    try:
        from app.database import async_session
        from app.services.sherlock_v3.instructions import load_instructions
        from app.services.sherlock_v3.verified_queries import retrieve_top_k

        async with async_session() as db:
            hits = await retrieve_top_k(
                user_message,
                tenant_id=tenant_id,
                app_id=app_id,
                db=db,
                k=5,
            )
            instructions_block = await load_instructions(
                app_id, tenant_id=tenant_id, db=db,
            )
        verified = tuple(
            VerifiedExampleRef(
                id=str(h.id), question=h.question, sql=h.sql,
                score=h.score, source=h.source,
            )
            for h in hits
        )
        return GroundingContext(
            app_id=app_id,
            user_message=user_message,
            verified_examples=verified,
            instructions_block=instructions_block,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            'sherlock_v3 grounding enrichment failed for app=%s: %s',
            app_id, exc,
        )
        return GroundingContext(app_id=app_id, user_message=user_message)


def _wrap_user_message_as_brief(
    *,
    user_message: str,
    ctx: SherlockTurnContext,
) -> str:
    """Always pass the supervisor a typed envelope as input — supervisor's prompt then crafts SpecialistBriefs for each as_tool dispatch."""
    return user_message


async def run_turn(
    user_message: str,
    ctx: SherlockTurnContext,
    *,
    max_turns: int = 10,
) -> TurnResult:
    """Execute one Sherlock v3 turn, emitting typed Parts via ctx.emitter."""
    if ctx.emitter is None:
        raise RuntimeError('SherlockTurnContext.emitter must be set before run_turn')

    client, supervisor_model = await get_sherlock_azure_client(
        tenant_id=ctx.tenant_id, call_site="analytics_supervisor",
    )
    _spec_client, specialist_model = await get_sherlock_azure_client(
        tenant_id=ctx.tenant_id, call_site="analytics_specialist",
    )
    del _spec_client

    grounding = await _compute_grounding(
        ctx.app_id, user_message, tenant_id=ctx.tenant_id,
    )
    supervisor = build_supervisor(
        ctx.app_id,
        client,
        supervisor_model=supervisor_model,
        specialist_model=specialist_model,
        grounding=grounding,
        builder_context=ctx.builder_context,
        auth=ctx.auth,
    )

    await ctx.emitter.emit(StepStartPart(
        id=new_part_id(),
        chat_session_id='',
        seq=0,
        created_at=0,
        turn_id=str(ctx.turn_id),
    ))
    await ctx.emitter.emit(UserMessagePart(
        id=new_part_id(),
        chat_session_id='',
        seq=0,
        created_at=0,
        text=user_message,
    ))

    try:
        usage, last_response_id = await _stream_once(
            supervisor, _wrap_user_message_as_brief(user_message=user_message, ctx=ctx),
            ctx, ctx.previous_response_id, max_turns,
        )
    except Exception as exc:
        if not _is_stale_previous_response_id(exc):
            await ctx.emitter.emit(ErrorPart(
                id=new_part_id(),
                chat_session_id='',
                seq=0,
                created_at=0,
                source='supervisor',
                message=f'{type(exc).__name__}: {exc}',
            ))
            await ctx.emitter.emit(StepFinishPart(
                id=new_part_id(),
                chat_session_id='',
                seq=0,
                created_at=0,
                turn_id=str(ctx.turn_id),
                status='error',
            ))
            return TurnResult(status='error', usage={}, last_response_id=None, error=str(exc))
        logger.warning(
            'sherlock_v3.run_turn previous_response_id is stale '
            '(>30d); replaying turn=%s without prior chain',
            ctx.turn_id,
        )
        try:
            replay_input = await _history_input_for_context(ctx)
            if not replay_input or replay_input[-1] != {'role': 'user', 'content': user_message}:
                replay_input.append({'role': 'user', 'content': user_message})
            usage, last_response_id = await _stream_once(
                supervisor, replay_input or user_message, ctx, None, max_turns,
            )
        except Exception as exc2:  # noqa: BLE001
            await ctx.emitter.emit(ErrorPart(
                id=new_part_id(),
                chat_session_id='',
                seq=0,
                created_at=0,
                source='supervisor',
                message=f'{type(exc2).__name__}: {exc2}',
            ))
            await ctx.emitter.emit(StepFinishPart(
                id=new_part_id(),
                chat_session_id='',
                seq=0,
                created_at=0,
                turn_id=str(ctx.turn_id),
                status='error',
            ))
            return TurnResult(status='error', usage={}, last_response_id=None, error=str(exc2))

    cumulative_tokens = await _session_cumulative_tokens(ctx)
    last_response_id, context_tokens_after = await _maybe_compact_supervisor(
        ctx=ctx,
        client=client,
        model=supervisor_model,
        last_response_id=last_response_id,
        cumulative_tokens=cumulative_tokens,
    )

    await ctx.emitter.emit(StepFinishPart(
        id=new_part_id(),
        chat_session_id='',
        seq=0,
        created_at=0,
        turn_id=str(ctx.turn_id),
        status='done',
        last_response_id=last_response_id,
        tokens_in=usage.get('input_tokens'),
        tokens_out=usage.get('output_tokens'),
        context_tokens=context_tokens_after,
        context_token_threshold=CONTEXT_COMPACT_THRESHOLD_TOKENS,
    ))
    return TurnResult(
        status='done',
        usage=usage,
        last_response_id=last_response_id,
    )


async def _stream_once(
    supervisor: Any,
    input_payload: Any,
    ctx: SherlockTurnContext,
    previous_response_id: str | None,
    max_turns: int,
) -> tuple[dict[str, Any], str | None]:
    streaming = Runner.run_streamed(
        supervisor,
        input_payload,
        context=ctx,
        max_turns=max_turns,
        previous_response_id=previous_response_id,
    )
    async for event in streaming.stream_events():
        await _emit_part_for_sdk_event(event, ctx)

    last_response_id = getattr(streaming, 'last_response_id', None)
    usage = _extract_usage(streaming)
    return usage, last_response_id


async def _session_cumulative_tokens(ctx: SherlockTurnContext) -> int:
    from sqlalchemy import select

    from app.database import async_session
    from app.models.sherlock_runtime import SherlockAgentSession

    async with async_session() as db:
        val = await db.scalar(
            select(SherlockAgentSession.cumulative_input_tokens)
            .where(SherlockAgentSession.chat_session_id == ctx.chat_session_id)
            .where(SherlockAgentSession.tenant_id == ctx.tenant_id)
            .where(SherlockAgentSession.user_id == ctx.user_id)
        )
    return int(val or 0)


async def _maybe_compact_supervisor(
    *,
    ctx: SherlockTurnContext,
    client: Any,
    model: str,
    last_response_id: str | None,
    cumulative_tokens: int,
) -> tuple[str | None, int]:
    """Compact the supervisor chain once accumulated context crosses the
    threshold, continuing from the compacted response id. Supervisor only —
    it owns the cross-turn previous_response_id chain; specialists are
    stateless per ``as_tool`` call. Trigger is the same
    ``cumulative_input_tokens`` the FE context ring reads, so UI and
    compaction stay in lockstep. The Azure v1 client exposes /responses/compact.

    Returns ``(last_response_id, context_tokens_after)``. The latter is 0 once
    compaction has fired — the cumulative counter is reset post-turn, so the
    ring drains immediately instead of sitting full until the next message."""
    if not last_response_id:
        return last_response_id, cumulative_tokens
    if cumulative_tokens < CONTEXT_COMPACT_THRESHOLD_TOKENS:
        return last_response_id, cumulative_tokens
    assert ctx.emitter is not None
    # Running → done in place (same id), mirroring ToolPart/SubtaskPart, so the
    # FE shows in-progress feedback during the non-instant compact() call.
    running = await ctx.emitter.emit(CompactionPart(
        id=new_part_id(),
        chat_session_id='',
        seq=0,
        created_at=0,
        status='running',
        tokens_before=cumulative_tokens,
    ))
    compacted = await client.responses.compact(
        model=model, previous_response_id=last_response_id,
    )
    await ctx.emitter.update(running.model_copy(update={'status': 'done'}))
    return compacted.id, 0


async def _emit_part_for_sdk_event(event: Any, ctx: SherlockTurnContext) -> None:
    """Translate one Agents-SDK stream event into Part emission.

    Supervisor text → AssistantTextPart streaming updates.
    Reasoning → ReasoningPart streaming updates.
    Supervisor's tool_called (calling a specialist) → SubtaskPart with brief.
    Server-side compaction → CompactionPart.
    Specialist's submit_sql lifecycle is owned by the specialist handler (ToolPart).
    """
    emitter = ctx.emitter
    assert emitter is not None
    event_type = type(event).__name__

    if event_type == 'RawResponsesStreamEvent':
        data = getattr(event, 'data', None)
        raw_type = str(getattr(data, 'type', '') or '')
        delta = getattr(data, 'delta', None)
        if isinstance(delta, str) and delta:
            if raw_type == 'response.output_text.delta':
                await _accrete_text_part(ctx, kind='assistant_text', delta=delta)
                return
            if raw_type == 'response.reasoning_summary_text.delta':
                await _accrete_text_part(ctx, kind='reasoning', delta=delta)
                return
        if 'compact' in raw_type.lower():
            comp = _compaction_payload(raw_type, data)
            if comp is not None:
                await emitter.emit(CompactionPart(
                    id=new_part_id(),
                    chat_session_id='',
                    seq=0,
                    created_at=0,
                    summary=comp.get('summary', ''),
                    tokens_before=comp.get('tokens_before'),
                ))
        if raw_type in (
            'response.output_text.done',
            'response.reasoning_summary_text.done',
            'response.completed',
        ):
            await _finalize_active_text_part(ctx)
        return

    if event_type == 'RunItemStreamEvent':
        item_name = getattr(event, 'name', '')
        if item_name == 'tool_called':
            tool_call = getattr(event, 'item', None)
            specialist = _tool_call_name(tool_call)
            call_id = _tool_call_call_id(tool_call) or f'call_{uuid.uuid4().hex[:12]}'
            # Retries now live inside the specialist (bounded submit_sql loop,
            # S1-8); the supervisor no longer re-dispatches for a retry, so the
            # RetryPart is emitted off the in-handler attempt_no, not here. A
            # repeat dispatch here is composition (a different sub-question).
            brief = await _tool_call_brief(tool_call, ctx=ctx)
            emitted = await emitter.emit(SubtaskPart(
                id=new_part_id(),
                chat_session_id='',
                seq=0,
                created_at=0,
                specialist=specialist,
                call_id=call_id,
                brief=brief,
                state=SubtaskStateRunning(started_at=int(time.monotonic() * 1000)),
            ))
            ctx.scratch.setdefault('_subtask_parts_by_call_id', {})[call_id] = emitted
            return
        if item_name == 'tool_output':
            await _close_subtask_on_output(getattr(event, 'item', None), ctx)
        return

    logger.debug('sherlock_v3 unhandled SDK stream event type: %s', event_type)


def _tool_output_text(item: Any) -> str:
    output = getattr(item, 'output', None)
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        return json.dumps(output, default=str)
    return ''


async def _close_subtask_on_output(output_item: Any, ctx: SherlockTurnContext) -> None:
    """Resolve the matching SubtaskPart's lifecycle when the specialist returns."""
    emitter = ctx.emitter
    if emitter is None or output_item is None:
        return
    call_id = _tool_call_call_id(output_item)
    subtask = ctx.scratch.get('_subtask_parts_by_call_id', {}).get(call_id)
    if subtask is None:
        return
    output_text = _tool_output_text(output_item)
    await _emit_canvas_patch_artifacts(output_text, ctx)
    result, is_error = project_specialist_output(
        subtask.specialist, output_text,
    )
    started_at = subtask.state.started_at if isinstance(subtask.state, SubtaskStateRunning) else 0
    ended_at = int(time.monotonic() * 1000)
    new_state = (
        SubtaskStateError(started_at=started_at, ended_at=ended_at, error=result.summary or 'specialist failed')
        if is_error
        else SubtaskStateCompleted(started_at=started_at, ended_at=ended_at, result=result)
    )
    await emitter.update(subtask.model_copy(update={'state': new_state}))


async def _emit_canvas_patch_artifacts(output_text: str, ctx: SherlockTurnContext) -> None:
    """Emit one CanvasPatchPart per canvas_patch artifact in a specialist's output.

    Mirrors the data_specialist's ChartPart emit, but the authoring patch is
    produced inside the pack's apply_patch handler (off the v3 emitter), so the
    runtime projects it here. Gated STRICTLY on CANVAS_PATCH_CONTRACT_ID — never
    promotes an arbitrary artifact kind. Runs once per tool output (keyed by
    call_id upstream), so a retried apply_patch yields its own output + part.
    """
    emitter = ctx.emitter
    if emitter is None or not output_text.strip():
        return
    try:
        decoded = json.loads(output_text)
    except (ValueError, TypeError):
        return
    if not isinstance(decoded, dict):
        return
    artifacts = decoded.get('artifacts')
    if not isinstance(artifacts, list):
        return
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        if artifact.get('kind') != CANVAS_PATCH_CONTRACT_ID:
            continue
        payload = artifact.get('payload')
        if not isinstance(payload, dict):
            continue
        try:
            patch = CanvasPatch.model_validate(payload)
        except Exception as exc:  # noqa: BLE001 — tolerant projection boundary
            logger.warning('sherlock_v3 canvas_patch artifact failed validation: %s', exc)
            continue
        await emitter.emit(CanvasPatchPart(
            id=new_part_id(),
            chat_session_id='',
            seq=0,
            created_at=0,
            patch=patch,
        ))


async def _accrete_text_part(
    ctx: SherlockTurnContext,
    *,
    kind: str,
    delta: str,
) -> None:
    """Stream tokens into an active AssistantTextPart / ReasoningPart, emitting on first delta + updating thereafter."""
    emitter = ctx.emitter
    assert emitter is not None
    scratch_key = f'_active_{kind}_part'
    active = ctx.scratch.get(scratch_key)
    if active is None:
        if kind == 'assistant_text':
            part = AssistantTextPart(
                id=new_part_id(),
                chat_session_id='',
                seq=0,
                created_at=0,
                text=delta,
            )
        else:
            part = ReasoningPart(
                id=new_part_id(),
                chat_session_id='',
                seq=0,
                created_at=0,
                text=delta,
            )
        emitted = await emitter.emit(part)
        ctx.scratch[scratch_key] = emitted
        return
    updated = active.model_copy(update={'text': (active.text or '') + delta})
    await emitter.update(updated)
    ctx.scratch[scratch_key] = updated


async def _finalize_active_text_part(ctx: SherlockTurnContext) -> None:
    """Mark whichever streaming Part is open as final + clear scratch."""
    emitter = ctx.emitter
    assert emitter is not None
    for key in ('_active_assistant_text_part', '_active_reasoning_part'):
        active = ctx.scratch.pop(key, None)
        if active is None:
            continue
        finalized = active.model_copy(update={'final': True})
        await emitter.update(finalized)


def _tool_call_name(item: Any) -> str:
    raw = getattr(item, 'raw_item', item)
    if isinstance(raw, dict):
        return str(raw.get('name') or 'data_specialist')
    return str(getattr(raw, 'name', '') or 'data_specialist')


def _tool_call_call_id(item: Any) -> str:
    raw = getattr(item, 'raw_item', item)
    if isinstance(raw, dict):
        return str(raw.get('call_id') or '')
    return str(getattr(raw, 'call_id', '') or '')


async def _tool_call_brief(item: Any, *, ctx: SherlockTurnContext) -> SpecialistBrief:
    """Parse the supervisor's tool args into a typed SpecialistBrief, emitting an ErrorPart when the payload does not match — so a malformed brief is visible in the timeline instead of silently downgraded."""
    raw = getattr(item, 'raw_item', item)
    args = raw.get('arguments') if isinstance(raw, dict) else getattr(raw, 'arguments', None)
    scope = SpecialistScope(
        tenant_id=str(ctx.tenant_id),
        app_id=ctx.app_id,
        user_id=str(ctx.user_id),
    )
    emitter = ctx.emitter
    if not (isinstance(args, str) and args.strip()):
        return SpecialistBrief(question=str(args or '')[:2000], scope=scope)
    try:
        payload = json.loads(args)
    except json.JSONDecodeError as exc:
        if emitter is not None:
            await emitter.emit(ErrorPart(
                id=new_part_id(),
                chat_session_id='',
                seq=0,
                created_at=0,
                source='supervisor',
                message=f'SpecialistBrief was not valid JSON: {exc.msg}',
                recoverable=True,
            ))
        return SpecialistBrief(question=args[:2000], scope=scope)
    if not isinstance(payload, dict):
        if emitter is not None:
            await emitter.emit(ErrorPart(
                id=new_part_id(),
                chat_session_id='',
                seq=0,
                created_at=0,
                source='supervisor',
                message='SpecialistBrief must be a JSON object',
                recoverable=True,
            ))
        return SpecialistBrief(question=str(payload)[:2000], scope=scope)
    try:
        return SpecialistBrief.model_validate({
            'question': payload.get('question') or '',
            'scope': scope.model_dump(),
            'prior_attempts': payload.get('prior_attempts') or [],
            'retry_hint': payload.get('retry_hint'),
        })
    except Exception as exc:  # noqa: BLE001
        if emitter is not None:
            await emitter.emit(ErrorPart(
                id=new_part_id(),
                chat_session_id='',
                seq=0,
                created_at=0,
                source='supervisor',
                message=f'SpecialistBrief failed validation: {exc}',
                recoverable=True,
            ))
        return SpecialistBrief(
            question=str(payload.get('question') or payload.get('task') or args)[:2000],
            scope=scope,
        )


def _compaction_payload(raw_type: str, data: Any) -> dict[str, Any] | None:
    if 'compaction' not in raw_type.lower():
        return None
    summary_text = ''
    tokens_before: int | None = None
    item = getattr(data, 'item', None)
    if item is not None:
        summary_text = (
            getattr(item, 'summary', None)
            or getattr(item, 'text', None)
            or getattr(item, 'content', None)
            or ''
        )
        token_field = getattr(item, 'tokens_before', None) or getattr(item, 'compacted_tokens', None)
        if isinstance(token_field, int):
            tokens_before = token_field
    if not summary_text:
        compaction = getattr(data, 'compaction', None)
        if compaction is not None:
            summary_text = getattr(compaction, 'summary', '') or ''
    return {'summary': str(summary_text or ''), 'tokens_before': tokens_before}


async def _history_input_for_context(ctx: SherlockTurnContext) -> list[dict[str, str]]:
    from app.database import async_session
    from app.models.chat import ChatMessage
    from sqlalchemy import select

    async with async_session() as db:
        rows = (
            await db.execute(
                select(ChatMessage.role, ChatMessage.content)
                .where(
                    ChatMessage.session_id == ctx.chat_session_id,
                    ChatMessage.tenant_id == ctx.tenant_id,
                    ChatMessage.user_id == ctx.user_id,
                    ChatMessage.status.in_(('complete', 'streaming')),
                    ChatMessage.role.in_(('user', 'assistant')),
                )
                .order_by(ChatMessage.created_at, ChatMessage.id)
            )
        ).all()
    return [
        {'role': role, 'content': content}
        for role, content in rows
        if role in {'user', 'assistant'} and content
    ]


def _extract_usage(streaming: Any) -> dict[str, Any]:
    ctx_wrapper = getattr(streaming, 'context_wrapper', None)
    usage = getattr(ctx_wrapper, 'usage', None) if ctx_wrapper else None
    if usage is None:
        return {
            'input_tokens': 0, 'output_tokens': 0, 'cached_read_tokens': 0,
            'cost_usd': 0.0, 'call_count': 0,
        }
    return {
        'input_tokens': getattr(usage, 'input_tokens', 0),
        'output_tokens': getattr(usage, 'output_tokens', 0),
        'cached_read_tokens': getattr(usage, 'cached_input_tokens', 0),
        'cost_usd': 0.0,
        'call_count': getattr(usage, 'requests', 0),
    }


__all__ = [
    'MAX_SPECIALIST_ATTEMPTS',
    'SherlockTurnContext',
    'TurnResult',
    'run_turn',
]
