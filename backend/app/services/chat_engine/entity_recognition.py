"""Structured-output entity recognition before the Sherlock tool loop."""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.services.evaluators.llm_base import LoggingLLMWrapper, create_llm_provider
from app.services.evaluators.runner_utils import make_usage_callback
from app.services.evaluators.settings_helper import get_llm_settings_from_db
from app.services.report_builder.scratchpad_state import (
    build_previous_turn_context,
    build_resolved_entity_context,
)
_APP_SCOPE_SPLIT_PATTERN = re.compile(r'[^a-z0-9]+')
_RUN_NAME_ENTITY_TYPES = {'run_name', 'run_reference'}
_EXPLICIT_RUN_NAME_PATTERNS = (
    re.compile(r'\brun[ _-]?name\b', re.IGNORECASE),
    re.compile(r'\bruns?\s+(named|called)\b', re.IGNORECASE),
    re.compile(r'\bnamed\s+["\']?[a-z0-9]', re.IGNORECASE),
    re.compile(r'\bcalled\s+["\']?[a-z0-9]', re.IGNORECASE),
)

_ENTITY_RECOGNITION_SYSTEM_PROMPT = """You classify whether a user question is within Sherlock's scope for the current application.

Rules:
- Return JSON only.
- Sherlock's in-scope domain includes the current application's runs, evaluations, trends, logs, rules, metrics, threads, reports, raw evidence, and related investigation/workflow questions grounded in the app's data.
- is_platform_query=true when the user is asking Sherlock to inspect, explain, summarize, compare, verify, or organize something about the current app and its data.
- If previous_turn context is present, interpret terse corrections, refinements, rendering requests, and continuations relative to that previous turn before deciding the message is out of scope.
- Only set is_platform_query=false when the new turn clearly leaves the current app's data/workflow context even after considering previous_turn.
- is_platform_query=false for general knowledge, personal chat, creative writing, web search, coding help unrelated to the current app, or requests not grounded in the current app's data/surfaces.
- needs_resolution=true when the question is vague, refers to entities by partial name/ID, or needs schema/data lookup before analysis or evidence retrieval.
- Only emit entity types from the provided registry.
- Keep entities concise and preserve the user's original text where possible.
"""


class RecognizedEntity(BaseModel):
    text: str
    type: str
    confidence: float = Field(ge=0, le=1)


class EntityRecognitionResult(BaseModel):
    entities: list[RecognizedEntity] = Field(default_factory=list)
    is_platform_query: bool = True
    needs_resolution: bool = False
    out_of_scope_reason: str | None = None


async def recognize_entities(
    *,
    question: str,
    scratchpad: dict[str, Any] | None,
    entity_registry: list[dict[str, Any]],
    provider: str,
    model: str,
    tenant_id: str,
    user_id: str,
    app_id: str | None = None,
    turn_id: str | None = None,
    app_scope_terms: list[str] | None = None,
) -> EntityRecognitionResult:
    llm = await _create_entity_recognition_provider(
        provider=provider,
        model=model,
        tenant_id=tenant_id,
        user_id=user_id,
        app_id=app_id,
        turn_id=turn_id,
    )
    payload = await llm.generate_json(
        prompt=_build_entity_recognition_prompt(
            question=question,
            scratchpad=scratchpad,
            entity_registry=entity_registry,
            app_scope_terms=app_scope_terms,
        ),
        system_prompt=_ENTITY_RECOGNITION_SYSTEM_PROMPT,
        json_schema=EntityRecognitionResult.model_json_schema(),
    )
    result = _filter_to_registered_types(
        EntityRecognitionResult.model_validate(payload),
        entity_registry=entity_registry,
    )
    result = _filter_app_scope_alias_entities(
        question=question,
        result=result,
        app_scope_terms=app_scope_terms,
    )
    return result


def render_entity_recognition_context(result: EntityRecognitionResult) -> str:
    lines: list[str] = []
    if not result.is_platform_query:
        lines.extend([
            'Scope signal for this question:',
            '- This turn is out of scope for the current app and its data/workflow context.',
            '- Reply in Sherlock\'s voice.',
            '- For greetings or light banter, keep it warm and brief, then steer back to the app.',
            '- For other out-of-scope asks, refuse briefly, do not answer the topic itself, and redirect to the current app.',
            '- Do not use tools on this turn.',
        ])
        if result.out_of_scope_reason:
            lines.append(f'- Classifier note: {result.out_of_scope_reason}')
    if result.entities:
        lines.append('Recognized entities for this question:')
    else:
        return '\n'.join(lines)
    for entity in result.entities:
        lines.append(f"- {entity.type}: {entity.text} ({entity.confidence:.2f})")
    if result.needs_resolution:
        lines.append('- Resolve fuzzy entities with tools before analytics.')
    return '\n'.join(lines)


async def _create_entity_recognition_provider(
    *,
    provider: str,
    model: str,
    tenant_id: str,
    user_id: str,
    app_id: str | None = None,
    turn_id: str | None = None,
):
    creds = await get_llm_settings_from_db(
        tenant_id=tenant_id,
        user_id=user_id,
        provider_override=provider,
        auth_intent='interactive',
    )
    inner = create_llm_provider(
        provider=provider,
        api_key=creds.get('api_key', ''),
        model_name=model,
        service_account_path=creds.get('service_account_path', ''),
        azure_endpoint=creds.get('azure_endpoint', ''),
        api_version=creds.get('api_version', '2025-03-01-preview'),
        temperature=0,
    )

    # Skip cost recording when the caller didn't pass ownership context
    # (legacy callers, tests) — the inner provider works standalone.
    if not app_id:
        return inner

    try:
        tenant_uuid = uuid.UUID(tenant_id)
        user_uuid = uuid.UUID(user_id) if user_id else None
        owner_uuid = uuid.UUID(turn_id) if turn_id else None
    except (ValueError, TypeError):
        return inner

    usage_cb = make_usage_callback(
        tenant_id=tenant_uuid,
        user_id=user_uuid,
        app_id=app_id,
        owner_type='sherlock_turn',
        owner_id=owner_uuid,
        subsystem='sherlock',
    )
    wrapper = LoggingLLMWrapper(inner, usage_callback=usage_cb)
    wrapper.set_call_purpose('entity_recognition', stage_index=0)
    return wrapper


def _build_entity_recognition_prompt(
    *,
    question: str,
    scratchpad: dict[str, Any] | None,
    entity_registry: list[dict[str, Any]],
    app_scope_terms: list[str] | None = None,
) -> str:
    registry_lines = []
    for item in entity_registry:
        examples = ', '.join(str(example) for example in item.get('examples', [])[:5] if str(example).strip())
        description = str(item.get('description', '')).strip()
        line = f"- {item.get('name')}: {description or 'No description'}"
        if examples:
            line += f" Examples: {examples}"
        registry_lines.append(line)

    scratchpad_context = build_resolved_entity_context(scratchpad) or 'No prior resolved entities.'
    previous_turn = build_previous_turn_context(scratchpad)
    previous_turn_text = (
        json.dumps(previous_turn, ensure_ascii=True, sort_keys=True, indent=2)
        if isinstance(previous_turn, dict) and previous_turn
        else 'No previous turn context.'
    )
    registry_text = '\n'.join(registry_lines) if registry_lines else '- none'
    app_scope_line = _render_app_scope_prompt_line(app_scope_terms)
    return (
        f"Question:\n{question.strip()}\n\n"
        f"{app_scope_line}\n\n"
        f"Previous turn context:\n{previous_turn_text}\n\n"
        f"Prior session context:\n{scratchpad_context}\n\n"
        f"Entity type registry:\n{registry_text}\n\n"
        "Extract typed entities, decide if the question is within Sherlock's current-app scope, "
        "and mark needs_resolution when Sherlock should discover schema, resolve exact values, or inspect evidence first."
    )


def _filter_to_registered_types(
    result: EntityRecognitionResult,
    *,
    entity_registry: list[dict[str, Any]],
) -> EntityRecognitionResult:
    allowed_types = {
        str(item.get('name', '')).strip().lower()
        for item in entity_registry
        if str(item.get('name', '')).strip()
    }
    if not allowed_types:
        return EntityRecognitionResult(
            entities=[],
            is_platform_query=result.is_platform_query,
            needs_resolution=result.needs_resolution,
            out_of_scope_reason=result.out_of_scope_reason,
        )

    filtered_entities = [
        entity
        for entity in result.entities
        if entity.type.strip().lower() in allowed_types
    ]
    if len(filtered_entities) == len(result.entities):
        return result
    return EntityRecognitionResult(
        entities=filtered_entities,
        is_platform_query=result.is_platform_query,
        needs_resolution=result.needs_resolution,
        out_of_scope_reason=result.out_of_scope_reason,
    )


def derive_app_scope_terms(app_id: str | None, app_display_name: str | None = None) -> list[str]:
    candidates = [str(app_id or '').strip(), str(app_display_name or '').strip()]
    terms: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        normalized = _normalize_scope_text(raw)
        if not normalized:
            continue
        pieces = [piece for piece in normalized.split() if len(piece) >= 3]
        for term in (normalized, *pieces):
            if term and term not in seen:
                seen.add(term)
                terms.append(term)
    return terms


def _normalize_scope_text(text: str) -> str:
    return ' '.join(part for part in _APP_SCOPE_SPLIT_PATTERN.split(str(text or '').strip().lower()) if part)


def _render_app_scope_prompt_line(app_scope_terms: list[str] | None) -> str:
    normalized_terms = [term for term in (app_scope_terms or []) if term]
    if not normalized_terms:
        return 'Current application aliases: none provided.'
    rendered = ', '.join(dict.fromkeys(normalized_terms))
    return (
        'Current application aliases: '
        f'{rendered}. Treat these as the current app scope, not as run_name/run_reference values, '
        'unless the user explicitly asks about a run name.'
    )


def _filter_app_scope_alias_entities(
    *,
    question: str,
    result: EntityRecognitionResult,
    app_scope_terms: list[str] | None,
) -> EntityRecognitionResult:
    normalized_scope_terms = {
        _normalize_scope_text(term)
        for term in (app_scope_terms or [])
        if _normalize_scope_text(term)
    }
    if not normalized_scope_terms or _has_explicit_run_name_intent(question):
        return result

    filtered_entities = [
        entity
        for entity in result.entities
        if not _entity_is_app_scope_alias(entity=entity, normalized_scope_terms=normalized_scope_terms)
    ]
    if len(filtered_entities) == len(result.entities):
        return result
    return EntityRecognitionResult(
        entities=filtered_entities,
        is_platform_query=result.is_platform_query,
        needs_resolution=result.needs_resolution,
        out_of_scope_reason=result.out_of_scope_reason,
    )


def _entity_is_app_scope_alias(
    *,
    entity: RecognizedEntity,
    normalized_scope_terms: set[str],
) -> bool:
    entity_type = entity.type.strip().lower()
    if entity_type not in _RUN_NAME_ENTITY_TYPES:
        return False
    entity_text = _normalize_scope_text(entity.text)
    if not entity_text:
        return False
    return entity_text in normalized_scope_terms


def _has_explicit_run_name_intent(question: str) -> bool:
    return any(pattern.search(question) for pattern in _EXPLICIT_RUN_NAME_PATTERNS)
