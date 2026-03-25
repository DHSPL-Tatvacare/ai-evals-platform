# Phase 1: Backend — FlowConfig + Unified Pipeline Runner

## Goal

Replace the branching `if is_api_flow / else` runner with a FlowConfig-driven pipeline where both flows execute the same 3-step sequence (transcription, normalization, critique) with step behavior controlled by config, not conditional branches.

## Current State (Problems)

### voice_rx_runner.py

1. **Lines 276-379** (API flow) and **lines 381-541** (upload flow) are two entirely separate code paths sharing nothing
2. **Line 252**: `if normalize_original and not is_api_flow:` — normalization hardcoded off for API
3. **Lines 544-587**: Summary computation is two different blocks with different output keys
4. Each flow calls different parsers (`parse_critique_response` vs `parse_api_critique_response`)
5. Each flow stores results under different keys (`critique` vs `apiCritique`, `llmTranscript` vs `judgeOutput`)

### prompt_resolver.py

6. Variable availability is controlled by `use_segments` flag, which callers set manually per flow — fragile

## Design

### 1.1 FlowConfig Dataclass

```python
# New file: backend/app/services/evaluators/flow_config.py

from dataclasses import dataclass, field
from typing import Literal, Optional

FlowType = Literal["upload", "api"]

@dataclass(frozen=True)
class FlowConfig:
    """Immutable config that controls pipeline behavior for a single eval run."""

    flow_type: FlowType

    # ── Step enablement ──
    skip_transcription: bool = False
    normalize_original: bool = False

    # ── Flow-derived properties ──
    @property
    def requires_segments(self) -> bool:
        """Upload flow requires time-aligned segments."""
        return self.flow_type == "upload"

    @property
    def requires_rx_fields(self) -> bool:
        """API flow compares structured rx data."""
        return self.flow_type == "api"

    @property
    def use_segments_in_prompts(self) -> bool:
        """Whether prompt variables like {{time_windows}} are available."""
        return self.flow_type == "upload"

    @property
    def normalization_input_type(self) -> Literal["segments", "text"]:
        """What shape the normalization input will be."""
        return "segments" if self.flow_type == "upload" else "text"

    @property
    def total_steps(self) -> int:
        """Number of pipeline steps for progress tracking."""
        steps = 0
        if not self.skip_transcription:
            steps += 1
        if self.normalize_original:
            steps += 1
        steps += 1  # critique always runs
        return steps

    @classmethod
    def from_params(cls, params: dict, source_type: str) -> "FlowConfig":
        """Construct from job params and listing source_type."""
        flow_type: FlowType = "api" if source_type == "api" else "upload"
        return cls(
            flow_type=flow_type,
            skip_transcription=params.get("skip_transcription", False),
            normalize_original=params.get("normalize_original", False),
        )
```

**Why frozen=True**: The config is a snapshot. Once the eval starts, nothing changes it. This prevents bugs where mid-pipeline state changes behavior.

### 1.2 Unified Pipeline Structure

Replace the `if is_api_flow / else` block with three extracted async functions that FlowConfig parameterizes:

```python
# In voice_rx_runner.py — new structure

async def run_voice_rx_evaluation(job_id, params: dict) -> dict:
    # ... (existing setup: load listing, create eval_run, resolve LLM settings) ...

    flow = FlowConfig.from_params(params, listing.source_type or "upload")
    total_steps = flow.total_steps

    # ... (existing config_snapshot, with flow_type added) ...

    current_step = 0
    try:
        # ── STEP 1: Transcription ───────────────────────
        if not flow.skip_transcription:
            current_step += 1
            await _update_progress(job_id, current_step, total_steps,
                "Transcribing audio..." if flow.requires_segments else "Judge is transcribing audio...",
                listing_id, str(eval_run_id))
            await check_cancel()

            transcription_result = await _run_transcription(
                flow=flow,
                llm=_create_llm(transcription_model),
                listing=listing,
                audio_bytes=audio_bytes,
                mime_type=mime_type,
                prompt_text=transcription_prompt,
                schema=transcription_schema,
                prerequisites=prerequisites,
            )
            evaluation.update(transcription_result)
        else:
            # Skip: reuse previous transcript (works for both flows)
            transcription_result = await _reuse_previous_transcript(listing_id, flow)
            evaluation.update(transcription_result)

        await check_cancel()

        # ── STEP 2: Normalization (optional) ────────────
        if flow.normalize_original:
            current_step += 1
            await _update_progress(job_id, current_step, total_steps,
                "Normalizing transcript...", listing_id, str(eval_run_id))
            await check_cancel()

            norm_result = await _run_normalization(
                flow=flow,
                llm=_create_llm(norm_model),
                listing=listing,
                prerequisites=prerequisites,
            )
            evaluation.update(norm_result)

            await check_cancel()

        # ── STEP 3: Critique ───────────────────────────
        current_step += 1
        await _update_progress(job_id, current_step, total_steps,
            "Generating critique..." if flow.requires_segments else "Comparing outputs...",
            listing_id, str(eval_run_id))
        await check_cancel()

        critique_result = await _run_critique(
            flow=flow,
            llm=_create_llm(evaluation_model),
            listing=listing,
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            prompt_text=evaluation_prompt,
            schema=evaluation_schema,
            prerequisites=prerequisites,
            evaluation=evaluation,  # needs access to transcription output
        )
        evaluation.update(critique_result)

        evaluation["status"] = "completed"
        evaluation["flowType"] = flow.flow_type

        # ── STEP 4: Summary (always) ──────────────────
        summary_data = _build_summary(flow, evaluation)

        # ... (existing save-to-DB logic) ...
```

### 1.3 Step Functions

Each step function receives `FlowConfig` and returns a dict to merge into `evaluation`.

#### `_run_transcription()`

```python
async def _run_transcription(
    flow: FlowConfig, llm, listing, audio_bytes, mime_type,
    prompt_text, schema, prerequisites,
) -> dict:
    """
    Step 1: Transcription.

    Upload flow: Transcribe audio → segments with time alignment.
    API flow: Judge transcribes audio → flat transcript + structured data.

    Returns dict to merge into evaluation:
      Upload: { "judgeOutput": { "transcript": str, "segments": [...] } }
      API:    { "judgeOutput": { "transcript": str, "structuredData": {...} } }
    """
    resolve_ctx = {
        "listing": {
            "transcript": listing.transcript,
            "sourceType": flow.flow_type,
            "apiResponse": listing.api_response,
        },
        "prerequisites": prerequisites,
        "use_segments": flow.use_segments_in_prompts,
    }
    resolved = resolve_prompt(prompt_text, resolve_ctx)
    final_prompt = resolved["prompt"].replace("{{audio}}", "[Audio file attached]")

    if not schema:
        raise ValueError(f"No transcription schema configured for {flow.flow_type} flow.")

    response_text = await llm.generate_with_audio(
        prompt=final_prompt,
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        json_schema=schema,
    )

    if flow.requires_segments:
        # Upload flow: parse into segments structure
        transcript_data = parse_transcript_response(response_text)
        return {
            "judgeOutput": {
                "transcript": transcript_data.get("fullTranscript", ""),
                "segments": transcript_data.get("segments", []),
            },
        }
    else:
        # API flow: parse into transcript + structured data
        parsed, was_repaired = _safe_parse_json(response_text)
        warnings = []
        if was_repaired:
            warnings.append("Transcription response was truncated and auto-repaired")

        # Extract transcript text
        if "input" in parsed:
            judge_transcript = str(parsed["input"])
        elif "segments" in parsed:
            judge_transcript = "\n".join(
                f"[{s.get('speaker', 'Unknown')}]: {s.get('text', '')}"
                for s in parsed["segments"]
            )
        else:
            judge_transcript = json.dumps(parsed, ensure_ascii=False)

        judge_structured = parsed.get("rx", parsed)

        result = {
            "judgeOutput": {
                "transcript": judge_transcript,
                "structuredData": judge_structured,
            },
        }
        if warnings:
            result["warnings"] = warnings
        return result
```

#### `_reuse_previous_transcript()`

```python
async def _reuse_previous_transcript(listing_id: str, flow: FlowConfig) -> dict:
    """
    Skip transcription: reuse judgeOutput from the most recent completed eval_run.

    Works for both flows — reads `judgeOutput` from the prior run's unified result.
    Returns same shape as _run_transcription() so the caller doesn't care.

    Upload flow prior result has: judgeOutput.transcript + judgeOutput.segments
    API flow prior result has:    judgeOutput.transcript + judgeOutput.structuredData
    """
    async with async_session() as db:
        prev_run_result = await db.execute(
            select(EvalRun)
            .where(
                EvalRun.listing_id == uuid.UUID(listing_id) if isinstance(listing_id, str) else listing_id,
                EvalRun.eval_type == "full_evaluation",
                EvalRun.status == "completed",
            )
            .order_by(EvalRun.created_at.desc())
            .limit(1)
        )
        prev_run = prev_run_result.scalar_one_or_none()

    if not prev_run or not prev_run.result:
        raise ValueError("Cannot skip transcription: no previous completed eval_run found.")

    prev_result = prev_run.result
    judge_output = prev_result.get("judgeOutput")

    if not judge_output:
        raise ValueError("Cannot skip transcription: previous eval_run has no judgeOutput.")

    result = {"judgeOutput": judge_output}

    # Carry forward the transcription prompt used in the prior run
    prev_prompts = prev_result.get("prompts", {})
    if prev_prompts.get("transcription"):
        result["_reused_transcription_prompt"] = prev_prompts["transcription"]

    return result
```

**Key**: This reads `judgeOutput` (the unified key), not the old `llmTranscript`. Since old data is deleted before deployment, all prior runs will have the new shape.

#### `_run_normalization()`

```python
async def _run_normalization(
    flow: FlowConfig, llm, listing, prerequisites,
) -> dict:
    """
    Step 2: Normalization (optional).

    Transliterates source transcript from one script to another.
    Handles both input formats based on what the listing has:
      - dict with 'segments' → segment-level normalization (upload flow)
      - str → plain text normalization (API flow)

    Returns dict to merge into evaluation:
      { "normalizedOriginal": { "fullTranscript": str, "segments"?: [...] },
        "normalizationMeta": { "enabled": true, ... } }
    """
    target_script = prerequisites.get("targetScript",
                    prerequisites.get("target_script", "Roman"))
    source_script = prerequisites.get("sourceScript",
                    prerequisites.get("source_script", "Devanagari"))
    language = prerequisites.get("language", "the source language")

    # Determine input based on what the listing actually has (not flow flag)
    source_input = _get_normalization_source(listing, flow)

    if source_input is None:
        # Nothing to normalize — skip silently
        return {}

    normalized_data = await _normalize_transcript(
        llm=llm,
        transcript_input=source_input,
        source_script=source_script,
        target_script=target_script,
        language=language,
    )

    if not normalized_data:
        return {}

    return {
        "normalizedOriginal": normalized_data,
        "normalizationMeta": {
            "enabled": True,
            "sourceScript": source_script,
            "targetScript": target_script,
            "normalizedAt": datetime.now(timezone.utc).isoformat(),
        },
    }


def _get_normalization_source(listing, flow: FlowConfig):
    """
    Get the transcript to normalize from the listing.
    Inspects actual data, not just flow type.
    """
    if listing.transcript and isinstance(listing.transcript, dict):
        segments = listing.transcript.get("segments")
        if segments and len(segments) > 0:
            return listing.transcript  # dict with segments
        full = listing.transcript.get("fullTranscript")
        if full:
            return full  # plain text from transcript dict

    if listing.api_response and isinstance(listing.api_response, dict):
        input_text = listing.api_response.get("input")
        if input_text and isinstance(input_text, str) and len(input_text.strip()) > 0:
            return input_text  # plain string from API

    return None


async def _normalize_transcript(llm, transcript_input, source_script, target_script, language) -> dict | None:
    """
    Core normalization function. Accepts any format, returns consistent shape.

    Input: str or dict-with-segments
    Output: { "fullTranscript": str, "segments"?: [...] } or None
    """
    has_segments = (isinstance(transcript_input, dict)
                    and isinstance(transcript_input.get("segments"), list)
                    and len(transcript_input["segments"]) > 0)

    if has_segments:
        # ── Segment-level normalization ──
        prompt = NORMALIZATION_PROMPT.format(
            source_script=source_script,
            target_script=target_script,
            language=language,
            transcript_json=json.dumps(transcript_input, indent=2),
        )
        result = await llm.generate_json(prompt=prompt, json_schema=NORMALIZATION_SCHEMA)

        norm_segments = result.get("segments", [])
        if not norm_segments:
            return None

        orig_segments = transcript_input.get("segments", [])
        normalized_segments = []
        for idx, seg in enumerate(norm_segments):
            normalized_segments.append({
                "speaker": seg.get("speaker", "Unknown"),
                "text": seg.get("text", ""),
                "startTime": seg.get("startTime", "00:00:00"),
                "endTime": seg.get("endTime", "00:00:00"),
                "startSeconds": orig_segments[idx].get("startSeconds") if idx < len(orig_segments) else None,
                "endSeconds": orig_segments[idx].get("endSeconds") if idx < len(orig_segments) else None,
            })

        full_transcript = "\n".join(
            f"[{s['speaker']}]: {s['text']}" for s in normalized_segments
        )
        return {
            "fullTranscript": full_transcript,
            "segments": normalized_segments,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }
    else:
        # ── Plain text normalization ──
        text = transcript_input if isinstance(transcript_input, str) else str(transcript_input)
        prompt = NORMALIZATION_PROMPT_PLAIN.format(
            source_script=source_script,
            target_script=target_script,
            language=language,
            transcript_text=text,
        )
        result = await llm.generate_json(prompt=prompt, json_schema=NORMALIZATION_SCHEMA_PLAIN)

        normalized_text = result.get("normalized_text", "").strip()
        if not normalized_text:
            return None

        return {
            "fullTranscript": normalized_text,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }
```

#### `_run_critique()`

```python
async def _run_critique(
    flow: FlowConfig, llm, listing, audio_bytes, mime_type,
    prompt_text, schema, prerequisites, evaluation,
) -> dict:
    """
    Step 3: Critique/comparison.

    Upload flow: Segment-level comparison (original vs judge).
    API flow: Field-level comparison (API output vs judge output).

    Returns dict to merge into evaluation:
      { "critique": { unified shape — see OVERVIEW.md } }
    """
    judge_output = evaluation.get("judgeOutput", {})
    normalized = evaluation.get("normalizedOriginal")

    if flow.requires_segments:
        # ── Upload flow critique ──
        # Use normalized transcript if available, else original
        original_transcript = listing.transcript
        if normalized and "segments" in normalized:
            original_transcript = {**listing.transcript, **normalized}

        resolve_ctx = {
            "listing": {
                "transcript": original_transcript,
                "sourceType": flow.flow_type,
                "apiResponse": listing.api_response,
            },
            "ai_eval": {
                "llmTranscript": {
                    "fullTranscript": judge_output.get("transcript", ""),
                    "segments": judge_output.get("segments", []),
                },
            },
            "prerequisites": prerequisites,
            "use_segments": True,
        }
        resolved = resolve_prompt(prompt_text, resolve_ctx)
        final_prompt = resolved["prompt"].replace("{{audio}}", "[Audio file attached]")

        critique_text = await llm.generate_with_audio(
            prompt=final_prompt,
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            json_schema=schema,
        )

        original_segments = (original_transcript or {}).get("segments", [])
        llm_segments = judge_output.get("segments", [])

        raw_critique = parse_critique_response(
            critique_text, original_segments, llm_segments, llm.model_name,
        )

        # Normalize to unified shape
        return {
            "critique": {
                "flowType": "upload",
                "overallAssessment": raw_critique.get("overallAssessment", ""),
                "statistics": raw_critique.get("statistics", {}),
                "segments": raw_critique.get("segments", []),
                "assessmentReferences": raw_critique.get("assessmentReferences", []),
                "rawOutput": raw_critique,
                "generatedAt": raw_critique.get("generatedAt", ""),
                "model": raw_critique.get("model", ""),
            },
        }
    else:
        # ── API flow critique ──
        api_response = listing.api_response or {}
        judge_transcript = judge_output.get("transcript", "")
        judge_structured = judge_output.get("structuredData", {})

        api_output_text = (
            f"\n\n=== API OUTPUT ===\n"
            f"Transcript: {api_response.get('input', '')}\n\n"
            f"Structured Data:\n{json.dumps(api_response.get('rx', {}), indent=2)}"
        )
        judge_output_text = (
            f"\n\n=== JUDGE OUTPUT ===\n"
            f"Transcript: {judge_transcript}\n\n"
            f"Structured Data:\n{json.dumps(judge_structured, indent=2)}"
        )

        resolve_ctx = {
            "listing": {
                "transcript": listing.transcript,
                "sourceType": flow.flow_type,
                "apiResponse": listing.api_response,
            },
            "ai_eval": {
                "judgeOutput": {"structuredData": judge_structured},
            },
            "prerequisites": prerequisites,
            "use_segments": False,
        }
        resolved = resolve_prompt(prompt_text, resolve_ctx)
        final_prompt = resolved["prompt"].replace("{{audio}}", "[Audio file attached]")
        full_prompt = f"{final_prompt}{api_output_text}{judge_output_text}"

        critique_text = await llm.generate_with_audio(
            prompt=full_prompt,
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            json_schema=schema,
        )

        raw_critique = parse_api_critique_response(critique_text, llm.model_name)

        # Normalize to unified shape
        return {
            "critique": {
                "flowType": "api",
                "overallAssessment": raw_critique.get("overallAssessment", ""),
                "transcriptComparison": raw_critique.get("transcriptComparison"),
                "fieldCritiques": _extract_field_critiques_from_raw(raw_critique),
                "rawOutput": raw_critique.get("rawOutput", raw_critique),
                "generatedAt": raw_critique.get("generatedAt", ""),
                "model": raw_critique.get("model", ""),
            },
        }
```

### 1.4 Unified Summary Builder

```python
def _build_summary(flow: FlowConfig, evaluation: dict) -> dict | None:
    """Build a consistent summary regardless of flow type."""
    if evaluation.get("status") != "completed":
        return None

    critique = evaluation.get("critique", {})
    summary = {"flow_type": flow.flow_type}

    if flow.requires_segments:
        # Upload: count from segments
        segments = critique.get("segments", [])
        total = len(segments)
        if total > 0:
            stats = critique.get("statistics", {})
            matches = stats.get("matchCount", sum(
                1 for s in segments
                if (s.get("severity", "").lower() == "none"
                    or s.get("accuracy", "").lower() in ("match", "none"))
            ))
            summary["overall_accuracy"] = matches / total
            summary["total_items"] = total
            severity_dist = _count_severity(segments, key="severity")
            summary["severity_distribution"] = severity_dist
            summary["critical_errors"] = severity_dist.get("CRITICAL", 0)
            summary["moderate_errors"] = severity_dist.get("MODERATE", 0)
            summary["minor_errors"] = severity_dist.get("MINOR", 0)
            if stats.get("overallScore") is not None:
                summary["overall_score"] = stats["overallScore"]
    else:
        # API: count from fieldCritiques
        field_critiques = critique.get("fieldCritiques", [])
        total = len(field_critiques)
        if total > 0:
            matches = sum(1 for fc in field_critiques if fc.get("match", False))
            summary["overall_accuracy"] = matches / total
            summary["total_items"] = total
            severity_dist = _count_severity(field_critiques, key="severity")
            summary["severity_distribution"] = severity_dist
            summary["critical_errors"] = severity_dist.get("CRITICAL", 0)
            summary["moderate_errors"] = severity_dist.get("MODERATE", 0)
            summary["minor_errors"] = severity_dist.get("MINOR", 0)

        # Also check for well-known score keys from rawOutput
        raw = critique.get("rawOutput", {})
        for score_key in ["overall_score", "accuracy_score", "factual_integrity_score"]:
            if raw.get(score_key) is not None:
                summary["overall_score"] = raw[score_key]
                break

    return summary if len(summary) > 1 else None


def _count_severity(items: list, key: str = "severity") -> dict:
    """Count severity distribution from a list of items."""
    dist = {}
    for item in items:
        sev = str(item.get(key, "none")).upper()
        dist[sev] = dist.get(sev, 0) + 1
    return dist
```

### 1.5 New Constants (Plain-Text Normalization)

```python
NORMALIZATION_PROMPT_PLAIN = """You are an expert multilingual transliteration specialist.

TASK: Convert the following transcript text from {source_script} script to {target_script} script.
Source language: {language}

RULES:
1. Transliterate all text from {source_script} to {target_script} using standard conventions for {language}
2. Preserve proper nouns, technical/medical terminology, and widely-known abbreviations in their original form
3. Keep speaker labels (e.g., [Doctor]:, [Patient]:) unchanged
4. For code-switched content (multiple languages mixed), transliterate the {language} portions while keeping other language portions intact
5. If source and target scripts are the same, return the text unchanged
6. Preserve line breaks and formatting

INPUT TRANSCRIPT:
{transcript_text}

OUTPUT: Return the transliterated transcript text."""

NORMALIZATION_SCHEMA_PLAIN = {
    "type": "object",
    "properties": {
        "normalized_text": {
            "type": "string",
            "description": "The full transcript text transliterated to the target script"
        },
    },
    "required": ["normalized_text"],
}
```

### 1.6 No Legacy Keys

Old eval_runs are deleted before deployment (see OVERVIEW.md migration step). The runner produces ONLY the unified shape:
- `critique` — never `apiCritique`
- `judgeOutput` — never `llmTranscript`
- `flowType` — always present

No backward compat code. No fallback keys. One shape.

### 1.7 `_extract_field_critiques_from_raw()`

This is the backend equivalent of the frontend's `extractFieldCritiques()` — normalizes field critiques from either the classic `structuredComparison.fields` shape or the `rawOutput.field_critiques` shape:

```python
def _extract_field_critiques_from_raw(raw_critique: dict) -> list[dict]:
    """Extract normalized field critiques from API critique response."""
    # Classic shape
    if raw_critique.get("structuredComparison", {}).get("fields"):
        return raw_critique["structuredComparison"]["fields"]

    # Schema-driven shape (rawOutput.field_critiques)
    raw = raw_critique.get("rawOutput", raw_critique)
    if isinstance(raw.get("field_critiques"), list):
        result = []
        for fc in raw["field_critiques"]:
            is_pass = str(fc.get("verdict", "")).lower() == "pass"
            result.append({
                "fieldPath": str(fc.get("field_name", "")),
                "apiValue": fc.get("extracted_value"),
                "judgeValue": fc.get("correction") or fc.get("extracted_value"),
                "match": is_pass,
                "critique": str(fc.get("reasoning", "")),
                "severity": "none" if is_pass else ("critical" if fc.get("error_type") == "contradiction" else "moderate"),
                "confidence": "high",
                "evidenceSnippet": fc.get("evidence_snippet"),
            })
        return result

    return []
```

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `backend/app/services/evaluators/flow_config.py` | **CREATE** | FlowConfig dataclass |
| `backend/app/services/evaluators/voice_rx_runner.py` | **REWRITE** | FlowConfig-driven pipeline with extracted step functions |

**Unchanged**: `response_parser.py` (parsers stay as-is), `prompt_resolver.py` (already reads `use_segments` from context).

## Verification Checklist

### Pre-Implementation
- [ ] Read current `voice_rx_runner.py` completely — verify all branches are accounted for
- [ ] Read `response_parser.py` — confirm parser outputs haven't changed since last read
- [ ] Check existing eval_run result shapes in DB (both upload and API flow)

### Post-Implementation
- [ ] `docker compose up --build` — backend starts without import errors
- [ ] `npx tsc -b` — no frontend type errors (Phase 1 is backend-only)
- [ ] Trigger upload flow eval → check:
  - [ ] EvalRun.result has `judgeOutput`, `critique`, `flowType: "upload"`
  - [ ] EvalRun.result does NOT have `llmTranscript` (dead key)
  - [ ] EvalRun.summary has `flow_type`, `overall_accuracy`, `total_items`, `severity_distribution`
  - [ ] API logs created for each LLM call
  - [ ] Job progress messages correct (3 steps or 2 if skip_transcription)
- [ ] Trigger upload flow with normalization → check:
  - [ ] `normalizedOriginal.fullTranscript` populated
  - [ ] `normalizedOriginal.segments` populated (segment-level)
  - [ ] `normalizationMeta.enabled = true`
  - [ ] SourceTranscriptPane toggle appears in UI
- [ ] Trigger API flow eval → check:
  - [ ] EvalRun.result has `judgeOutput.transcript`, `judgeOutput.structuredData`
  - [ ] EvalRun.result has `critique.flowType: "api"`, `critique.fieldCritiques`
  - [ ] EvalRun.result does NOT have `apiCritique` (new shape)
  - [ ] Summary has same unified keys
- [ ] Trigger API flow with normalization → check:
  - [ ] `normalizedOriginal.fullTranscript` populated (plain text)
  - [ ] `normalizedOriginal` does NOT have `segments` (no segment data for API)
  - [ ] SourceTranscriptPane toggle appears
- [ ] Cancellation during each step → verify partial result saved, status="cancelled"
- [ ] Error in transcription → verify status="failed", error_message set
- [ ] Error in critique → verify status="failed", partial result preserved

### Edge Cases
- [ ] Skip transcription (upload) — reuses previous run's `judgeOutput` (with segments) correctly
- [ ] Skip transcription (API) — reuses previous run's `judgeOutput` (with structuredData) correctly
- [ ] Missing schema (API) — raises clear error before LLM call
- [ ] Normalization enabled but no source transcript — silently skips (returns `{}`)
- [ ] Normalization returns empty result — silently skips
- [ ] LLM returns truncated JSON — `_safe_parse_json` repair + warning flag
