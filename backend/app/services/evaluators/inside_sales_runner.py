"""Inside Sales call quality evaluation runner.

Two-step pipeline per call:
  1. TRANSCRIBE: Download MP3 from Ozonetel S3 → send audio to LLM via generate_with_audio → get transcript
  2. EVALUATE:   Send transcript + rubric prompt to LLM via generate_json → get dimension scores

Creates one EvalRun with eval_type='call_quality', one ThreadEvaluation per call.
"""

import asyncio
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
from app.services.job_worker import (
    is_job_cancelled,
    safe_error_message,
    update_job_progress,
)

logger = logging.getLogger(__name__)


async def run_inside_sales_evaluation(
    job_id: str,
    params: dict,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict:
    """Evaluate inside sales calls against rubric evaluators."""
    start_time = time.monotonic()

    # Extract params
    call_selection = params.get("call_selection", {})
    evaluator_ids = params.get("evaluator_ids", [])
    llm_config = params.get("llm_config", {})
    transcription_config = params.get("transcription_config", {})
    parallel_workers = params.get("parallel_workers", 3)
    run_name = params.get("run_name", "Inside Sales Eval")
    run_description = params.get("run_description", "")
    preview_calls = params.get("preview_calls", [])

    # Create eval_run immediately
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

    # Load evaluators
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

    # Resolve LLM credentials
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

    # Fetch calls to evaluate
    from app.services.lsq_client import fetch_call_activities, normalize_activity, hydrate_lead_names

    calls_to_evaluate: list[dict[str, Any]] = []

    if preview_calls:
        # Use preview calls from wizard (already normalized)
        calls_to_evaluate = preview_calls
    else:
        # Fetch from LSQ
        result = await fetch_call_activities(
            date_from=call_selection.get("date_from", ""),
            date_to=call_selection.get("date_to", ""),
            page=1,
            page_size=100,
        )
        calls_to_evaluate = [normalize_activity(a) for a in result.get("activities", [])]

        # Hydrate lead names
        pids = [c.get("prospectId", "") for c in calls_to_evaluate if c.get("prospectId")]
        if pids:
            names = await hydrate_lead_names(pids)
            for c in calls_to_evaluate:
                c["leadName"] = names.get(c.get("prospectId", ""), "")

    # Apply filters
    if call_selection.get("min_duration"):
        calls_to_evaluate = [c for c in calls_to_evaluate if (c.get("durationSeconds", 0) or 0) >= 10]
    if call_selection.get("agent"):
        agent = call_selection["agent"].lower()
        calls_to_evaluate = [c for c in calls_to_evaluate if agent in (c.get("agentName", "") or "").lower()]
    if call_selection.get("direction"):
        calls_to_evaluate = [c for c in calls_to_evaluate if c.get("direction") == call_selection["direction"]]

    # Apply selection mode
    mode = call_selection.get("selection_mode", "all")
    if mode == "sample":
        import random
        sample_size = call_selection.get("sample_size", 20)
        if len(calls_to_evaluate) > sample_size:
            calls_to_evaluate = random.sample(calls_to_evaluate, sample_size)
    elif mode == "specific":
        specific_ids = set(call_selection.get("selected_call_ids", []))
        if specific_ids:
            calls_to_evaluate = [c for c in calls_to_evaluate if c.get("activityId") in specific_ids]

    total = len(calls_to_evaluate)
    if total == 0:
        await finalize_eval_run(
            eval_run_id, tenant_id,
            status="completed",
            duration_ms=(time.monotonic() - start_time) * 1000,
            summary={"total": 0, "evaluated": 0},
        )
        return {"status": "completed", "total": 0, "evaluated": 0}

    # Process calls
    evaluated = 0
    failed = 0
    total_score_sum = 0.0
    semaphore = asyncio.Semaphore(parallel_workers)

    async def process_call(idx: int, call: dict) -> None:
        nonlocal evaluated, failed, total_score_sum

        if await is_job_cancelled(job_id):
            return

        async with semaphore:
            call_id = call.get("activityId", f"call-{idx}")
            agent = call.get("agentName", "Unknown")
            lead = call.get("leadName", "Unknown")
            recording_url = call.get("recordingUrl", "")

            llm.set_thread_id(call_id)

            try:
                # ── Step 1: Transcribe ──────────────────────────────
                transcript = ""

                if recording_url:
                    await update_job_progress(
                        job_id, idx, total,
                        f"Transcribing call {idx + 1}/{total}...",
                    )

                    # Download MP3 from Ozonetel S3
                    async with httpx.AsyncClient(timeout=60) as http:
                        audio_resp = await http.get(recording_url)
                        audio_resp.raise_for_status()
                        audio_bytes = audio_resp.content

                    # Determine mime type from URL
                    mime_type = "audio/mpeg"
                    if recording_url.lower().endswith(".wav"):
                        mime_type = "audio/wav"

                    # Transcribe via LLM (same as Voice Rx step 1)
                    transcription_prompt = (
                        "Transcribe this sales call recording. "
                        "Identify two speakers: the sales agent and the customer/lead. "
                        "Output the full conversation as a transcript with speaker labels. "
                        "Use format: [Agent]: ... and [Lead]: ... for each turn. "
                        "Transcribe in the original language (likely Hindi or Hindi-English mix). "
                        "Include all dialogue, even small talk and greetings."
                    )

                    transcript = await llm.generate_with_audio(
                        prompt=transcription_prompt,
                        audio_bytes=audio_bytes,
                        mime_type=mime_type,
                        system_prompt="You are an expert multilingual transcriptionist. Transcribe sales calls accurately with speaker diarization.",
                    )

                    if not transcript or not transcript.strip():
                        transcript = "[Transcription returned empty result]"

                else:
                    transcript = (
                        f"[No recording available for this call]\n"
                        f"Agent: {agent}, Lead: {lead}, "
                        f"Duration: {call.get('durationSeconds', 0)}s, "
                        f"Status: {call.get('status', 'unknown')}"
                    )
                    if call.get("callNotes"):
                        transcript += f"\nCall Notes: {call['callNotes']}"

                # ── Step 2: Evaluate against rubric ─────────────────
                await update_job_progress(
                    job_id, idx, total,
                    f"Evaluating call {idx + 1}/{total}...",
                )

                for evaluator in evaluators:
                    prompt = evaluator["prompt"].replace("{{transcript}}", transcript)
                    output_schema = evaluator["output_schema"]
                    json_schema = generate_json_schema(output_schema)

                    result = await llm.generate_json(
                        prompt=prompt,
                        json_schema=json_schema,
                    )

                    parsed = _safe_parse_json(result) if isinstance(result, str) else result
                    if not parsed:
                        parsed = {"error": "Failed to parse LLM response"}

                    # Extract overall score
                    main_field = find_primary_field(output_schema)
                    overall_score = parsed.get(main_field["key"]) if main_field else None
                    if isinstance(overall_score, (int, float)):
                        total_score_sum += overall_score

                    # Store ThreadEvaluation
                    async with async_session() as db:
                        db.add(ThreadEvaluation(
                            run_id=eval_run_id,
                            thread_id=call_id,
                            result={
                                "evaluator_id": evaluator["id"],
                                "evaluator_name": evaluator["name"],
                                "output": parsed,
                                "transcript": transcript,
                                "call_metadata": {
                                    "agent": agent,
                                    "lead": lead,
                                    "direction": call.get("direction"),
                                    "duration": call.get("durationSeconds"),
                                    "recording_url": recording_url,
                                },
                            },
                            success_status=True,
                        ))
                        await db.commit()

                evaluated += 1

            except Exception as e:
                logger.error("Failed to evaluate call %s: %s", call_id, e)
                failed += 1

                async with async_session() as db:
                    db.add(ThreadEvaluation(
                        run_id=eval_run_id,
                        thread_id=call_id,
                        result={"error": safe_error_message(e)},
                        success_status=False,
                    ))
                    await db.commit()

            await update_job_progress(
                job_id, idx + 1, total,
                f"Processed {idx + 1}/{total} calls",
            )

    # Run all calls
    tasks = [process_call(i, call) for i, call in enumerate(calls_to_evaluate)]
    await asyncio.gather(*tasks)

    # Finalize
    duration_ms = (time.monotonic() - start_time) * 1000
    avg_score = total_score_sum / evaluated if evaluated > 0 else None

    summary = {
        "total": total,
        "evaluated": evaluated,
        "failed": failed,
        "average_score": round(avg_score, 1) if avg_score is not None else None,
        "evaluator_names": [e["name"] for e in evaluators],
        "overall_score": avg_score,
    }

    await finalize_eval_run(
        eval_run_id, tenant_id,
        status="completed" if failed == 0 else "completed",
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
        "status": "completed",
        "run_id": str(eval_run_id),
        **summary,
    }


