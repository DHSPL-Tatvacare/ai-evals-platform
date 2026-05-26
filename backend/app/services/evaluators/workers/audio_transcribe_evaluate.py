"""Audio call worker: download recording → transcribe → evaluate against rubrics.

One worker per call recording. Shell handles parallelism, persistence, and
lifecycle. This module only knows how to turn one EvaluableCall + a set of
evaluators into a `WorkerOutput`.

Naming: this worker is generic by capability, not by app. Any app whose
DatasetBinding produces EvaluableCall records can reference
`audio_transcribe_evaluate` from its App.config.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.services.analytics.signal_taxonomy import SIGNAL_TYPES
from app.services.evaluators.evaluation_constants import (
    NORMALIZATION_PROMPT_PLAIN,
    NORMALIZATION_SYSTEM_PROMPT,
    build_normalization_schema_plain,
    resolve_script_name,
)
from app.services.evaluators.output_schema_utils import primary_score
from app.services.evaluators.response_parser import _safe_parse_json
from app.services.evaluators.runner_utils import set_usage_call_purpose
from app.services.evaluators.schema_generator import generate_json_schema
from app.services.evaluators.workers.types import (
    EvaluatorOutput,
    WorkerContext,
    WorkerOutput,
)

logger = logging.getLogger(__name__)


# ── Recording-missing sentinel ───────────────────────────────────────


class RecordingMissingError(RuntimeError):
    """Raised when an EvaluableCall has no recording_url. The shell catches
    this and persists it as a per-thread error, so the run still summarises
    cleanly with one failed thread instead of crashing the whole job."""


# ── Signals contract — append the runtime-only `signals` field ──────


def _signal_field_description() -> str:
    enum_inline = ", ".join(sorted(SIGNAL_TYPES))
    return (
        "Coaching signals extracted from this call. Emit one entry per "
        "discrete signal (commitments, intents, objections, outcomes, etc.). "
        f"Use one of the controlled signal_type values: {enum_inline}. If "
        "none of the controlled types fit, use 'other_notable_signal' and "
        "describe the raw label inside attributes.signal_type_raw. Return an "
        "empty array when no signals are present in the call."
    )


def _build_signals_field_definition() -> dict[str, Any]:
    return {
        "key": "signals",
        "type": "array",
        "description": _signal_field_description(),
        "arrayItemSchema": {
            "itemType": "object",
            "properties": [
                {"key": "signal_type", "type": "string", "description": "Canonical signal type."},
                {"key": "signal_value", "type": "string", "description": "Optional canonical short value."},
                {"key": "signal_value_numeric", "type": "number", "description": "Optional numeric value."},
                {"key": "signal_at", "type": "string", "description": "Optional ISO-8601 timestamp."},
                {"key": "confidence", "type": "number", "description": "Optional 0..1 confidence."},
                {"key": "supporting_quote", "type": "string", "description": "Optional verbatim quote."},
                {"key": "attributes", "type": "object", "description": "Optional free-form metadata."},
            ],
        },
    }


def _augment_output_schema(output_schema: list[dict]) -> list[dict]:
    """Return an augmented copy with the runtime-only `signals` field appended.

    Original `output_schema` is the evaluator's stored rubric and is consumed
    by `primary_score()` / visible breakdown — it MUST NOT be mutated.
    """
    return list(output_schema or []) + [_build_signals_field_definition()]


def _normalize_signal_entry(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    signal_type = (raw.get("signal_type") or "").strip()
    if not signal_type:
        return None
    return {
        "signal_type": signal_type,
        "signal_value": raw.get("signal_value") or None,
        "signal_value_numeric": raw.get("signal_value_numeric"),
        "signal_at": raw.get("signal_at") or None,
        "confidence": raw.get("confidence"),
        "supporting_quote": raw.get("supporting_quote") or None,
        "attributes": raw.get("attributes") or {},
    }


def merge_signals(eval_outputs: list[EvaluatorOutput]) -> list[dict]:
    """Merge per-evaluator `output['signals']` into one canonical array.

    De-dup key: (signal_type, signal_value, signal_at, supporting_quote).
    First occurrence wins. This canonical merged array is what `populate-
    analytics` reads from `evaluation_run_thread_results.result.signals`.
    """
    merged: list[dict] = []
    seen: set[tuple] = set()
    for ev in eval_outputs or []:
        signals = (ev.output or {}).get("signals") or []
        if not isinstance(signals, list):
            continue
        for raw in signals:
            entry = _normalize_signal_entry(raw)
            if entry is None:
                continue
            key = (
                entry["signal_type"],
                entry["signal_value"],
                entry["signal_at"],
                entry["supporting_quote"],
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(entry)
    return merged


# ── Transcription prompt ─────────────────────────────────────────────


# Structured transcription contract — no free-form string extraction.
_TRANSCRIPTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "transcript": {
            "type": "string",
            "description": "Full verbatim transcript, with [Agent]:/[Lead]: labels when diarization is requested.",
        },
        "detected_script": {
            "type": "string",
            "description": "Lowercase id of the script the transcript is written in (e.g. latin, devanagari, tamil, arabic, cjk).",
        },
    },
    "required": ["transcript", "detected_script"],
}


def _build_transcription_prompt(config: dict[str, Any]) -> tuple[str, str]:
    """Generic transcription prompt. `language` is a display name from the shared
    registry (e.g. "Hindi", "Tamil", "Auto-detect") — there is no per-language map;
    the name is interpolated directly, and the script registry resolves the script."""
    language = (config.get("language") or "auto").strip()
    script_id = config.get("script", "auto")
    diarize = config.get("speaker_diarization", config.get("speakerDiarization", True))
    preserve_cs = config.get(
        "preserve_code_switching", config.get("preserveCodeSwitching", True)
    )
    script_display = resolve_script_name(script_id)  # "" for auto
    auto_lang = language.lower() in ("", "auto", "auto-detect")

    parts = ["Transcribe this sales call recording verbatim, including greetings and small talk."]
    if auto_lang:
        parts.append(
            "Detect the spoken language(s) and transcribe faithfully in the original "
            "language(s) — do not guess or default to any specific language."
        )
    else:
        parts.append(f"The call is in {language}. Transcribe it in {language}.")
    if script_display:
        parts.append(f"Write the transcript in {script_display} script.")
    if diarize:
        parts.append("Identify the two speakers and label each turn as [Agent]: or [Lead]:.")
    if preserve_cs:
        parts.append("Preserve code-switching between languages exactly as spoken.")
    parts.append("Never translate — keep the spoken language exactly.")
    parts.append(
        'Also report the script you wrote the transcript in via "detected_script" '
        "as a lowercase id such as latin, devanagari, tamil, arabic, or cjk."
    )

    sys_prompt = (
        "You are an expert multilingual transcriptionist for sales calls. "
        "Transcribe verbatim, never translate, and return only the requested JSON object."
    )
    return " ".join(parts), sys_prompt


def _mime_for_url(url: str) -> str:
    return "audio/wav" if url.lower().endswith(".wav") else "audio/mpeg"


# ── Optional transliteration stage ──────────────────────────────────


async def _maybe_transliterate(
    ctx: WorkerContext, transcript: str, detected_script: str
) -> tuple[str | None, dict[str, Any] | None]:
    """Optional stage: transliterate the transcript into the target script.

    Same language, script conversion only (Devanagari → Roman). Reuses voice-rx's
    plain-text normalization prompt/schema. Runs on the evaluation LLM (text->text).
    Returns (transliterated_text, meta) or (None, None) when disabled/skipped/empty.
    """
    cfg = ctx.transcription_config
    if not cfg.get("transliterate"):
        return None, None

    target_script = cfg.get("target_script", "latin")
    # Smart gate: the transcription model reports the script it produced. If the
    # transcript is already in the target script there is nothing to convert, so
    # skip the LLM call instead of round-tripping for an unchanged result.
    if detected_script and detected_script == target_script.strip().lower():
        return None, None

    target_display = resolve_script_name(target_script) or target_script
    source_script = detected_script or cfg.get("script", "auto")
    source_display = resolve_script_name(source_script)
    language = cfg.get("language", "auto")

    if not source_display or source_script == "auto":
        source_instruction = "The source script should be auto-detected from the input text."
    else:
        source_instruction = f"The source text is in {source_display} script."

    set_usage_call_purpose(ctx.evaluation_llm, "transliteration", stage_index=2)
    raw = await ctx.evaluation_llm.generate_json(
        prompt=NORMALIZATION_PROMPT_PLAIN.format(
            target_script=target_display,
            source_instruction=source_instruction,
            language=language,
            transcript_text=transcript,
        ),
        system_prompt=NORMALIZATION_SYSTEM_PROMPT,
        json_schema=build_normalization_schema_plain(target_display),
    )
    parsed = _safe_parse_json(raw)[0] if isinstance(raw, str) else raw
    text = ((parsed or {}).get("normalized_text") or "").strip()
    if not text:
        return None, None
    return text, {
        "enabled": True,
        "source_script": source_script,
        "target_script": target_script,
    }


# ── Worker entry point ───────────────────────────────────────────────


async def audio_transcribe_evaluate(ctx: WorkerContext) -> WorkerOutput:
    """Transcribe the call's recording, run each evaluator, return a WorkerOutput."""
    record = ctx.record
    if not record.recording_url:
        raise RecordingMissingError(
            f"Call {record.activity_id} has no recording_url"
        )

    transcription_prompt, transcription_sys = _build_transcription_prompt(
        ctx.transcription_config
    )

    # ── Step 1: Download + Transcribe ────────────────────────────
    async with httpx.AsyncClient(timeout=60) as http:
        audio_resp = await http.get(record.recording_url)
        audio_resp.raise_for_status()
        audio_bytes = audio_resp.content

    set_usage_call_purpose(ctx.transcription_llm, "transcription", stage_index=0)
    raw_transcription = await ctx.transcription_llm.generate_with_audio(
        prompt=transcription_prompt,
        audio_bytes=audio_bytes,
        mime_type=_mime_for_url(record.recording_url),
        system_prompt=transcription_sys,
        json_schema=_TRANSCRIPTION_SCHEMA,
    )
    parsed_transcription = (
        _safe_parse_json(raw_transcription)[0]
        if isinstance(raw_transcription, str)
        else raw_transcription
    ) or {}
    transcript = (parsed_transcription.get("transcript") or "").strip()
    detected_script = (parsed_transcription.get("detected_script") or "").strip().lower()
    if not transcript:
        transcript = "[Transcription returned empty result]"

    # ── Step 1.5: Optional transliteration (gated by the detected script) ──
    transcript_transliterated, transliteration_meta = await _maybe_transliterate(
        ctx, transcript, detected_script
    )

    # ── Step 2: Evaluate against each rubric ─────────────────────
    eval_outputs: list[EvaluatorOutput] = []
    for evaluator in ctx.evaluators:
        prompt = evaluator.prompt.replace("{{transcript}}", transcript)
        augmented = _augment_output_schema(evaluator.output_schema)
        json_schema = generate_json_schema(augmented)

        set_usage_call_purpose(ctx.evaluation_llm, "evaluation", stage_index=1)
        raw_result = await ctx.evaluation_llm.generate_json(
            prompt=prompt,
            json_schema=json_schema,
        )
        parsed = (
            _safe_parse_json(raw_result)[0]
            if isinstance(raw_result, str)
            else raw_result
        )
        if not parsed:
            parsed = {"error": "Failed to parse LLM response"}

        eval_outputs.append(
            EvaluatorOutput(
                evaluator_id=str(evaluator.id),
                evaluator_name=evaluator.name,
                output=parsed,
                score=primary_score(parsed, evaluator.output_schema),
            )
        )

    return WorkerOutput(
        transcript=transcript,
        evaluator_outputs=eval_outputs,
        signals=merge_signals(eval_outputs),
        transcript_transliterated=transcript_transliterated,
        transliteration_meta=transliteration_meta,
    )


__all__ = [
    "RecordingMissingError",
    "audio_transcribe_evaluate",
    "merge_signals",
]
