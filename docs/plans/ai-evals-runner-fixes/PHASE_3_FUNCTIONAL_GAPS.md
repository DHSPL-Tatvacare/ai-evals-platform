# Phase 3: Functional Gaps

**Goal:** Fix M2 — the `thinking` parameter not being passed through in custom evaluator LLM calls.
**Risk Level:** Low — adding a parameter to existing function calls. No structural changes.
**Files Changed:** `custom_evaluator_runner.py` only
**Prerequisite:** Phase 1 and Phase 2 must be completed first.

---

## Bug M2: `thinking` Param Ignored in Custom Evaluator

### Problem

Every runner passes the `thinking` parameter through to LLM calls — except `custom_evaluator_runner.py`.

**Evidence — how other runners pass `thinking`:**

```python
# batch_runner.py L298 (intent evaluator):
intent_results = await w_intent_eval.evaluate_thread(thread.messages, thinking=thinking)

# batch_runner.py L338-341 (custom evaluator within batch):
output = await worker_llm.generate_json(
    prompt=prompt_text,
    json_schema=json_schema,
    thinking=thinking,
)

# adversarial_runner.py L183 (test case generation):
cases = await evaluator.generate_test_cases(
    test_count, thinking=thinking, extra_instructions=extra_instructions,
)

# voice_rx_runner.py L537 (transcription):
response_text = await llm.generate_with_audio(
    prompt=final_prompt,
    audio_bytes=audio_bytes,
    mime_type=mime_type,
    json_schema=schema,
    thinking=thinking,
)

# voice_rx_runner.py L685 (normalization):
result = await llm.generate_json(prompt=prompt, json_schema=schema, thinking=thinking)
```

**The gap — `custom_evaluator_runner.py` L267-281:**

```python
# thinking = params.get("thinking", "low")   ← extracted at L219, never used

# L268-274 (audio path):
if has_audio and audio_bytes:
    response_text = await llm.generate_with_audio(
        prompt=prompt_text,
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        json_schema=json_schema,
        # thinking NOT passed
    )

# L276-280 (text path):
else:
    output = await llm.generate_json(
        prompt=prompt_text,
        json_schema=json_schema,
        # thinking NOT passed
    )
```

### User Impact

When a user selects "High" thinking (for higher quality evaluations) or "None" (for faster/cheaper runs) from the UI for a custom evaluator job, the selection is:
1. Sent to the backend in job params (**correct**)
2. Extracted from params at L219 (**correct**)
3. Never passed to the LLM provider (**bug**)

The LLM provider uses its default thinking level, which is typically "low" or provider-dependent. The user's selection is silently ignored.

This affects:
- **voice-rx custom evals** (single listing with optional audio)
- **kaira-bot custom evals** (single chat session)
- **Custom evals triggered by evaluate-custom-batch** (since `run_custom_eval_batch` delegates to `run_custom_evaluator`)

This does NOT affect:
- Standard voice-rx pipeline (`evaluate-voice-rx`) — passes thinking correctly
- Batch thread evaluation (`evaluate-batch`) — passes thinking correctly (including for custom evaluators within batch, which use a separate code path at batch_runner.py L338)
- Adversarial evaluation (`evaluate-adversarial`) — passes thinking correctly

### Fix

Add `thinking=thinking` to both LLM calls in `run_custom_evaluator`.

**BEFORE** (L268-281):
```python
if has_audio and audio_bytes:
    response_text = await llm.generate_with_audio(
        prompt=prompt_text,
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        json_schema=json_schema,
    )
    output, _was_repaired = _safe_parse_json(response_text)
else:
    output = await llm.generate_json(
        prompt=prompt_text,
        json_schema=json_schema,
    )
    response_text = json.dumps(output, ensure_ascii=False)
```

**AFTER**:
```python
if has_audio and audio_bytes:
    response_text = await llm.generate_with_audio(
        prompt=prompt_text,
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        json_schema=json_schema,
        thinking=thinking,
    )
    output, _was_repaired = _safe_parse_json(response_text)
else:
    output = await llm.generate_json(
        prompt=prompt_text,
        json_schema=json_schema,
        thinking=thinking,
    )
    response_text = json.dumps(output, ensure_ascii=False)
```

### What NOT to Change

- Do NOT change `thinking` extraction at L219. `params.get("thinking", "low")` is correct and matches other runners.
- Do NOT add `thinking` to `run_custom_eval_batch` — it delegates to `run_custom_evaluator` which will now handle it.
- Do NOT change the `config_snapshot` at L231-239. It doesn't include `thinking` currently, and that's acceptable (other runners include it in `batch_metadata`, but single custom evals don't use batch_metadata).

### Optional Enhancement (Not Required)

Consider adding `thinking` to the config snapshot for auditability:

```python
config_snapshot = {
    "prompt": evaluator.prompt,
    "resolved_prompt": prompt_text,
    "output_schema": evaluator.output_schema,
    "model_id": model,
    "provider": db_settings["provider"],
    "evaluator_name": evaluator.name,
    "auth_method": db_settings["auth_method"],
    "thinking": thinking,  # <-- optional: audit trail
}
```

This is cosmetic (no functional impact) but aligns with how other runners record the thinking level in their metadata.

---

## Verify: `generate_with_audio` and `generate_json` Accept `thinking` Kwarg

Before implementing, confirm that both LLM methods accept `thinking` as a keyword argument. Check `backend/app/services/evaluators/llm_base.py`:

```python
# Expected signatures (verify these exist):
async def generate_with_audio(self, prompt, audio_bytes, mime_type, json_schema=None, thinking="low"):
async def generate_json(self, prompt, json_schema, thinking="low"):
```

If the signatures use `**kwargs` instead, the `thinking` kwarg will be silently accepted and passed through. Either way, this fix is safe.

---

## Post-Fix Validation

### Functional Test

| # | Scenario | What to Verify |
|---|---|---|
| T1 | Custom eval (voice-rx, thinking="high") | Run custom evaluator on a voice-rx listing with thinking set to "high". Check API logs (`api_logs` table) for this eval_run — the LLM call should include thinking configuration. Compare token usage with a "low" thinking run — "high" should use more tokens. |
| T2 | Custom eval (kaira-bot, thinking="none") | Run custom evaluator on a kaira-bot session with thinking="none". Verify the LLM call completes faster and/or with fewer tokens than "low". |
| T3 | Custom eval with audio (voice-rx) | Run a custom evaluator that uses `{{audio}}` on a voice-rx listing. Verify `generate_with_audio` receives the thinking param (check API logs). |
| T4 | Custom eval batch | Run `evaluate-custom-batch` with 2+ evaluators. Verify each sub-evaluator's LLM calls include the thinking configuration from the parent job's params. |

### Regression Check

| # | Flow | What to Verify |
|---|---|---|
| R1 | Custom eval without thinking param | `params.get("thinking", "low")` defaults to "low". Verify existing behavior unchanged for jobs that don't specify thinking. |
| R2 | Batch thread eval with custom evaluators | `batch_runner.py` L338 already passes `thinking`. Verify this still works (no interference from the fix). |

### Cross-Runner Consistency Audit

After all 3 phases, verify that `thinking` is passed correctly in ALL LLM calls across ALL runners:

| Runner | LLM Call | Passes `thinking`? |
|---|---|---|
| `batch_runner.py` | IntentEvaluator.evaluate_thread (L298) | Yes |
| `batch_runner.py` | CorrectnessEvaluator.evaluate_thread (L307) | Yes |
| `batch_runner.py` | EfficiencyEvaluator.evaluate_thread (L316) | Yes |
| `batch_runner.py` | worker_llm.generate_json for custom (L338) | Yes |
| `adversarial_runner.py` | evaluator.generate_test_cases (L183) | Yes |
| `adversarial_runner.py` | evaluator.conversation_agent.run_conversation (L205) | Yes |
| `adversarial_runner.py` | evaluator.evaluate_transcript (L210) | Yes |
| `voice_rx_runner.py` | llm.generate_with_audio (L537) | Yes |
| `voice_rx_runner.py` | llm.generate_json for normalization (L685, L721) | Yes |
| `voice_rx_runner.py` | llm.generate_json for critique (L783, L865) | Yes |
| `custom_evaluator_runner.py` | llm.generate_with_audio (L269) | **After fix: Yes** |
| `custom_evaluator_runner.py` | llm.generate_json (L277) | **After fix: Yes** |
