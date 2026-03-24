"""Inside Sales call quality evaluation runner.

Two-step pipeline per call:
  1. TRANSCRIBE: Download MP3 from Ozonetel S3 → send audio to LLM via generate_with_audio → get transcript
  2. EVALUATE:   Send transcript + rubric prompt to LLM via generate_json → get dimension scores

Uses run_parallel engine for bounded concurrency, cancellation, and progress tracking.
Creates one EvalRun with eval_type='call_quality', one ThreadEvaluation per call.
"""

import logging
import time
import uuid
from typing import Any

import httpx
from sqlalchemy import select, or_, and_

from app.database import async_session
from app.models.eval_run import ThreadEvaluation
from app.models.evaluator import Evaluator
from app.constants import SYSTEM_TENANT_ID
from app.services.evaluators.llm_base import (
    LoggingLLMWrapper,
    create_llm_provider,
)
from app.services.evaluators.runner_utils import (
    save_api_log,
    create_eval_run,
    finalize_eval_run,
    find_primary_field,
)
from app.services.evaluators.schema_generator import generate_json_schema
from app.services.evaluators.response_parser import _safe_parse_json
from app.services.evaluators.settings_helper import get_llm_settings_from_db
from app.services.evaluators.parallel_engine import run_parallel
from app.services.job_worker import (
    safe_error_message,
    update_job_progress,
)

logger = logging.getLogger(__name__)


# ── Transcription prompt builder ─────────────────────────────────────


def _build_transcription_prompt(config: dict) -> tuple[str, str]:
    """Build transcription prompt and system prompt from wizard config.

    Returns: (prompt, system_prompt)
    """
    lang = config.get("language", "hi-en")
    lang_map = {
        "hi": "Hindi",
        "en": "English",
        "hi-en": "Hindi-English (code-mixed)",
        "auto": "auto-detect the language",
    }
    lang_display = lang_map.get(lang, lang)
    diarize = config.get("speakerDiarization", True)

    prompt = f"Transcribe this sales call recording in {lang_display}. "
    if diarize:
        prompt += (
            "Identify two speakers: the sales agent and the customer/lead. "
            "Use format: [Agent]: ... and [Lead]: ... for each turn. "
        )
    prompt += (
        "Include all dialogue, even small talk and greetings. "
        "Preserve the original language — do not translate."
    )
    if config.get("preserveCodeSwitching", True):
        prompt += " Preserve code-switching between Hindi and English as spoken."

    sys_prompt = (
        f"You are an expert multilingual transcriptionist specializing in "
        f"{lang_display} sales calls. Transcribe accurately"
        f"{' with speaker diarization' if diarize else ''}."
    )

    return prompt, sys_prompt


# ── Main entry point ─────────────────────────────────────────────────


async def run_inside_sales_evaluation(
    job_id: str,
    params: dict,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict:
    """Evaluate inside sales calls against rubric evaluators."""
    start_time = time.monotonic()

    # ── Extract params ───────────────────────────────────────────
    call_selection = params.get("call_selection", {})
    evaluator_ids = params.get("evaluator_ids", [])
    llm_config = params.get("llm_config", {})
    transcription_config = params.get("transcription_config", {})
    parallel_workers = params.get("parallel_workers", 3)
    run_name = params.get("run_name", "Inside Sales Eval")
    run_description = params.get("run_description", "")

    # ── Create EvalRun immediately (visible in UI) ───────────────
    eval_run_id = uuid.uuid4()

    await create_eval_run(
        id=eval_run_id,
        tenant_id=tenant_id,
        user_id=user_id,
        app_id="inside-sales",
        eval_type="call_quality",
        job_id=job_id,
        llm_provider=llm_config.get("provider"),
        llm_model=llm_config.get("model"),
        batch_metadata={
            "run_name": run_name,
            "run_description": run_description,
            "call_selection": call_selection,
            "evaluator_count": len(evaluator_ids),
        },
    )

    await update_job_progress(
        job_id, 0, 1, "Loading evaluators...",
        run_id=str(eval_run_id),
    )

    # ── Load evaluators ──────────────────────────────────────────
    evaluators: list[dict[str, Any]] = []
    async with async_session() as db:
        for eid in evaluator_ids:
            ev = await db.scalar(
                select(Evaluator).where(
                    Evaluator.id == eid,
                    or_(
                        and_(Evaluator.tenant_id == tenant_id, Evaluator.user_id == user_id),
                        Evaluator.tenant_id == SYSTEM_TENANT_ID,
                    ),
                )
            )
            if ev:
                evaluators.append({
                    "id": str(ev.id),
                    "name": ev.name,
                    "prompt": ev.prompt,
                    "output_schema": ev.output_schema,
                })

    if not evaluators:
        await finalize_eval_run(
            eval_run_id, tenant_id,
            status="failed",
            duration_ms=(time.monotonic() - start_time) * 1000,
            error_message="No evaluators found",
        )
        return {"status": "failed", "error": "No evaluators found"}

    # ── Resolve LLM credentials ──────────────────────────────────
    llm_settings = await get_llm_settings_from_db(
        tenant_id, user_id,
        app_id="inside-sales",
        auth_intent="managed_job",
        provider_override=llm_config.get("provider"),
    )

    provider = create_llm_provider(
        provider=llm_settings.get("provider", llm_config.get("provider", "gemini")),
        api_key=llm_settings.get("api_key", ""),
        model_name=llm_config.get("model", llm_settings.get("selected_model", "")),
        temperature=llm_config.get("temperature", 0.1),
        service_account_path=llm_settings.get("service_account_path", ""),
    )
    llm = LoggingLLMWrapper(provider, log_callback=save_api_log)
    llm.set_context(str(eval_run_id))

    # ── Fetch ALL matching calls from LSQ ────────────────────────
    from app.services.lsq_client import fetch_call_activities, normalize_activity

    await update_job_progress(
        job_id, 0, 1, "Fetching calls from LeadSquared...",
        run_id=str(eval_run_id),
    )

    all_calls: list[dict[str, Any]] = []
    date_from = call_selection.get("date_from", "")
    date_to = call_selection.get("date_to", "")
    lsq_page = 1
    lsq_page_size = 100

    while True:
        result = await fetch_call_activities(
            date_from=date_from,
            date_to=date_to,
            event_codes=None,
            page=lsq_page,
            page_size=lsq_page_size,
        )
        activities = result.get("activities", [])
        if not activities:
            break
        all_calls.extend(normalize_activity(a) for a in activities)
        if len(activities) < lsq_page_size:
            break
        lsq_page += 1

    logger.info("Fetched %d total calls from LSQ (%d pages)", len(all_calls), lsq_page)

    # ── Apply filters ────────────────────────────────────────────
    calls = all_calls
    if call_selection.get("min_duration"):
        calls = [c for c in calls if (c.get("durationSeconds", 0) or 0) >= 10]
    if call_selection.get("agent"):
        agent_filter = call_selection["agent"].lower()
        calls = [c for c in calls if agent_filter in (c.get("agentName", "") or "").lower()]
    if call_selection.get("direction"):
        calls = [c for c in calls if c.get("direction") == call_selection["direction"]]

    # Skip calls without recordings — no audio = nothing to transcribe
    skipped_no_recording = len([c for c in calls if not c.get("recordingUrl")])
    calls = [c for c in calls if c.get("recordingUrl")]

    # Apply selection mode
    mode = call_selection.get("selection_mode", "all")
    if mode == "sample":
        import random
        sample_size = call_selection.get("sample_size", 20)
        if len(calls) > sample_size:
            calls = random.sample(calls, sample_size)
    elif mode == "specific":
        specific_ids = set(call_selection.get("selected_call_ids", []))
        if specific_ids:
            calls = [c for c in calls if c.get("activityId") in specific_ids]

    total = len(calls)
    logger.info(
        "After filters: %d calls to evaluate (%d skipped, no recording)",
        total, skipped_no_recording,
    )

    if total == 0:
        await finalize_eval_run(
            eval_run_id, tenant_id,
            status="completed",
            duration_ms=(time.monotonic() - start_time) * 1000,
            summary={
                "total": 0, "evaluated": 0, "failed": 0,
                "skipped_no_recording": skipped_no_recording,
            },
        )
        return {"status": "completed", "total": 0, "evaluated": 0}

    # ── Build transcription prompt once (shared across all calls) ─
    transcription_prompt, transcription_sys = _build_transcription_prompt(transcription_config)

    # ── Worker function for run_parallel ─────────────────────────

    async def _evaluate_one_call(index: int, call: dict) -> dict:
        """Transcribe + evaluate a single call.

        Returns result dict for post-run aggregation.
        Each worker gets its own LLM clone for thread-safe context.
        """
        call_id = call.get("activityId", f"call-{index}")
        recording_url = call.get("recordingUrl", "")

        # Thread-safe LLM clone
        worker_llm = llm.clone_for_thread(call_id)

        # ── Step 1: Download + Transcribe ────────────────────
        async with httpx.AsyncClient(timeout=60) as http:
            audio_resp = await http.get(recording_url)
            audio_resp.raise_for_status()
            audio_bytes = audio_resp.content

        mime_type = "audio/mpeg"
        if recording_url.lower().endswith(".wav"):
            mime_type = "audio/wav"

        transcript = await worker_llm.generate_with_audio(
            prompt=transcription_prompt,
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            system_prompt=transcription_sys,
        )

        if not transcript or not transcript.strip():
            transcript = "[Transcription returned empty result]"

        # ── Step 2: Evaluate against each rubric ─────────────
        eval_outputs: list[dict] = []
        overall_score = None

        for evaluator in evaluators:
            prompt = evaluator["prompt"].replace("{{transcript}}", transcript)
            output_schema = evaluator["output_schema"]
            json_schema = generate_json_schema(output_schema)

            raw_result = await worker_llm.generate_json(
                prompt=prompt,
                json_schema=json_schema,
            )

            parsed = _safe_parse_json(raw_result) if isinstance(raw_result, str) else raw_result
            if not parsed:
                parsed = {"error": "Failed to parse LLM response"}

            main_field = find_primary_field(output_schema)
            score = parsed.get(main_field["key"]) if main_field else None

            if overall_score is None and isinstance(score, (int, float)):
                overall_score = score

            eval_outputs.append({
                "evaluator_id": evaluator["id"],
                "evaluator_name": evaluator["name"],
                "output": parsed,
            })

        # ── Step 3: Persist ThreadEvaluation ─────────────────
        async with async_session() as db:
            db.add(ThreadEvaluation(
                run_id=eval_run_id,
                thread_id=call_id,
                result={
                    "evaluations": eval_outputs,
                    "transcript": transcript,
                    "call_metadata": {
                        "agent": call.get("agentName", ""),
                        "lead": call.get("prospectId", ""),
                        "direction": call.get("direction"),
                        "duration": call.get("durationSeconds"),
                        "recording_url": recording_url,
                    },
                },
                success_status=True,
            ))
            await db.commit()

        return {
            "call_id": call_id,
            "overall_score": overall_score,
            "is_error": False,
        }

    # ── Progress callback for run_parallel ────────────────────────

    async def _progress_cb(current: int, total_count: int, message: str):
        await update_job_progress(job_id, current, total_count, message)

    def _progress_msg(ok: int, err: int, current: int, tot: int) -> str:
        return f"Call {current}/{tot} ({ok} ok, {err} errors)"

    # ── Run with parallel engine ─────────────────────────────────

    try:
        results = await run_parallel(
            items=calls,
            worker=_evaluate_one_call,
            concurrency=parallel_workers,
            job_id=job_id,
            tenant_id=tenant_id,
            progress_callback=_progress_cb,
            progress_message=_progress_msg,
            inter_item_delay=0.5,
        )
    except Exception as e:
        logger.error("run_parallel failed: %s", e)
        await finalize_eval_run(
            eval_run_id, tenant_id,
            status="failed",
            duration_ms=(time.monotonic() - start_time) * 1000,
            error_message=safe_error_message(e),
        )
        return {"status": "failed", "error": safe_error_message(e)}

    # ── Collect results ──────────────────────────────────────────

    evaluated = 0
    failed = 0
    scores: list[float] = []

    for r in results:
        if isinstance(r, BaseException):
            failed += 1
            # Store error as ThreadEvaluation for visibility
            async with async_session() as db:
                db.add(ThreadEvaluation(
                    run_id=eval_run_id,
                    thread_id=f"error-{failed}",
                    result={"error": safe_error_message(r)},
                    success_status=False,
                ))
                await db.commit()
        elif isinstance(r, dict):
            if r.get("is_error"):
                failed += 1
            else:
                evaluated += 1
                if isinstance(r.get("overall_score"), (int, float)):
                    scores.append(r["overall_score"])

    avg_score = round(sum(scores) / len(scores), 1) if scores else None

    # ── Finalize ─────────────────────────────────────────────────

    duration_ms = (time.monotonic() - start_time) * 1000
    summary = {
        "total": total,
        "evaluated": evaluated,
        "failed": failed,
        "skipped_no_recording": skipped_no_recording,
        "average_score": avg_score,
        "evaluator_names": [e["name"] for e in evaluators],
        "overall_score": avg_score,
    }

    final_status = "completed" if failed == 0 else "completed_with_errors"

    await finalize_eval_run(
        eval_run_id, tenant_id,
        status=final_status,
        duration_ms=duration_ms,
        summary=summary,
        config={
            "run_name": run_name,
            "evaluator_count": len(evaluators),
            "evaluator_name": evaluators[0]["name"] if evaluators else "",
            "call_count": total,
            "parallel_workers": parallel_workers,
        },
    )

    return {
        "status": final_status,
        "run_id": str(eval_run_id),
        **summary,
    }
