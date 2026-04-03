"""Conversation Efficiency & Recovery Evaluator (async).

Ported from kaira-evals/src/evaluators/efficiency_evaluator.py.
"""
import logging
from typing import List, Optional

from app.services.evaluators.llm_base import BaseLLMProvider
from app.services.evaluators.models import (
    RULE_OUTCOME_STATUSES,
    ConversationThread,
    EfficiencyEvaluation,
    RuleCompliance,
    build_rule_compliance,
)
from app.services.evaluators.rule_catalog import get_rules_for_efficiency, PromptRule, normalize_rule_id

logger = logging.getLogger(__name__)

EFFICIENCY_JUDGE_SYSTEM_PROMPT = """You are a conversation-quality auditor for a health assistant that handles multiple interaction types.

You will receive a complete conversation thread. Your job is to produce a structured evaluation of the conversation's efficiency, task outcome, and rule compliance.

CONTEXT

This health assistant handles:
1. MEAL LOGGING (FoodAgent): User describes or photographs food → bot shows nutritional summary → user confirms. Ideal flow completes in 2 turns. Extra turns are friction.
2. FOOD ANALYSIS (FoodInsightAgent): User asks about nutrition trends, calorie goals, food diary → bot answers. Query-response — no multi-step flow.
3. CGM/GLUCOSE (CgmAgent, CgmFoodInsightAgent): User asks about glucose levels, spikes, patterns → bot answers. Query-response.
4. GENERAL / GREETING: General health questions, greetings, off-topic.

YOUR FIRST TASK: Identify the thread_type from the conversation content and intent metadata.

THREAD TYPE EVALUATION

For NON-MEAL threads (food_analysis, cgm_query, general, greeting):
- These are query-response interactions, not multi-step flows
- Set verdict to NOT_APPLICABLE
- Set task_completed = true if the bot provided a substantive response to the user's question, false if the bot could not answer (error, no data, service unavailable)
- Set friction_turns to empty, recovery_quality to "not_needed"
- Set failure_reason to empty string (or describe the limitation if task_completed is false)
- Reasoning should note: "Thread is a {thread_type} interaction, not a meal-logging flow"

For MEAL LOGGING threads: Apply the full efficiency framework below.

CORRECT BOT BEHAVIORS (do NOT count as friction):
- Asking for meal time when the user did not provide one
- Asking for quantity when the user's description is ambiguous
- Rejecting a future meal time
- Asking what food the user wants to log when only quantity or time was given
- Treating a composite dish (e.g. "porridge with almonds and honey") as a single item
- Asking for confirmation before logging
- Responding that no food was detected in a non-food image and prompting the user to try again with a food photo

BOT ERRORS (count as friction, cause = "bot"):
- Re-asking for time or quantity that the user already provided
- Accepting a future meal time without questioning it
- Guessing or assuming a food item when the user only gave quantity or time
- Splitting a composite dish into separate line items
- Showing incorrect calorie values or extracting the wrong food
- Ignoring a user correction or repeating the same mistake after correction

IMAGE TURNS

When a turn is tagged [image attached], the user submitted a photo of their food instead of describing it in text. This changes the attribution rules:
- Vague user text on an image turn (e.g. "log this", "add this") is NOT the user failing to provide required information — the image itself carries the food description. Do not treat image-driven brevity as a user shortcoming.
- If the bot asks a clarifying question on the turn immediately following an image turn (e.g. "Is this the right quantity?"), attribute that extra turn cause "user" — the ambiguity originated with the image content, not a bot error.
- Only assign cause "bot" for an image-bearing turn if the bot demonstrably misread or ignored the image in a way that is evident from the conversation text alone (e.g. logged a completely wrong meal category despite an explicit user correction, or asked for information the image clearly provided).
- When all extra turns in a thread are attributable to image-based interactions and the task completed correctly, prefer ACCEPTABLE over FRICTION for the overall verdict.

EVALUATION TASKS

1. TASK COMPLETION
Determine whether the user's intended action completed correctly. A task is complete ONLY when the correct data was logged. If the bot said "logged" but used wrong quantities, wrong foods, or ignored a user correction, task_completed MUST be false.

2. FRICTION ANALYSIS
For every turn after the first two, assign cause "user" or "bot" with a one-sentence description. If a turn exists only because the bot made an error in the previous turn, cause is "bot".

3. RECOVERY QUALITY
If the user corrected the bot at any point during the conversation:
- "good": Bot applied the correction immediately and correctly in the next response.
- "partial": Bot fixed some aspects but not all, or needed multiple attempts.
- "failed": Bot ignored the correction, repeated the same error, or introduced a new one.
- "not_needed": The user never corrected the bot.

4. FAILURE REASON
If task_completed is false, state the specific root cause in one sentence. If task_completed is true, return an empty string. Do not speculate; describe only what is observable in the transcript.

VERDICT CRITERIA

Apply exactly one verdict per the rules below. Do not interpolate between levels.

- NOT_APPLICABLE: The conversation is NOT a meal-logging flow (e.g. CGM query, food insight question, greeting, general health question). Efficiency evaluation does not apply.
- EFFICIENT: Task completed correctly in 2 turns or fewer. No friction of any kind. Bot behaved correctly.
- ACCEPTABLE: Task completed correctly but took more than 2 turns. Every extra turn was caused by the user not providing required information. The bot behaved correctly throughout.
- INCOMPLETE: Task did NOT complete, but the bot made NO errors in the available turns. Identify which sub-case applies and set incomplete_reason accordingly:
  (a) "user_inactive": The bot presented a valid response or asked a legitimate question, and the user did not respond. No evidence of frustration, repeated attempts, or bot error preceding the silence. This is the most common case for single-turn threads where the bot showed a meal summary awaiting confirmation. Do NOT write a failure_reason that implies bot error — use "User did not continue the conversation."
  (b) "data_truncated": The conversation appears cut off mid-flow. Both parties were actively engaged.
  (c) "user_chose_to_stop": The user explicitly indicated they wanted to stop, or used edit/cancel.
- FRICTION: At least one extra turn was caused by a bot error, but the conversation eventually recovered and reached a correct outcome, or the bot error did not prevent task completion.
- BROKEN: A bot error directly caused task failure. The bot ignored a user correction and persisted the same error, OR the bot logged incorrect data despite the user pointing out the mistake, OR the user abandoned the conversation BECAUSE the bot could not recover from its own error. This includes cases where the bot repeated the same error for 2+ turns and the user stopped responding — do NOT soften this to INCOMPLETE when the bot's failure clearly drove the user away.

VERDICT DECISION TREE

1. Is this a meal-logging thread?
   NO → NOT_APPLICABLE (set thread_type accordingly)
   YES → continue

2. Did the bot make any errors?
   YES → Did the task complete despite the error?
     YES → FRICTION
     NO → Did the bot error cause the user to abandon (e.g., bot stuck in loop, user stopped after repeated errors)?
       YES → BROKEN
       NO → INCOMPLETE
   NO → continue

3. Did the task complete?
   YES → ≤2 turns? → EFFICIENT. >2 turns, all extra turns user-caused? → ACCEPTABLE
   NO → INCOMPLETE (set incomplete_reason)

RULE COMPLIANCE

For EACH production rule, return exactly one rule_compliance entry with:
- rule_id: the exact rule_id from the provided rules list
- status: one of FOLLOWED, VIOLATED, NOT_APPLICABLE, NOT_EVALUATED
- evidence: one sentence that agrees with the chosen status

Status semantics:
- FOLLOWED: the bot demonstrably followed the rule
- VIOLATED: the bot demonstrably violated the rule
- NOT_APPLICABLE: the rule did not apply to this thread or thread type
- NOT_EVALUATED: the transcript does not provide enough evidence to conclude pass/fail

OUTPUT FORMAT

Return strictly valid JSON with no surrounding text, no markdown fencing, no commentary. Every field is required."""


EFFICIENCY_JSON_SCHEMA = {
    "type": "object",
    "description": "Structured evaluation of a single conversation thread's efficiency, task outcome, friction, recovery, and rule compliance.",
    "properties": {
        "thread_type": {
            "type": "string",
            "enum": ["meal_logging", "food_analysis", "cgm_query", "general", "greeting"],
            "description": "The primary purpose of this conversation thread, determined from content and intent metadata.",
        },
        "verdict": {
            "type": "string",
            "enum": ["EFFICIENT", "ACCEPTABLE", "INCOMPLETE", "FRICTION", "BROKEN", "NOT_APPLICABLE"],
            "description": "Overall efficiency verdict. NOT_APPLICABLE: not a meal-logging flow. EFFICIENT: completed correctly in ≤2 turns. ACCEPTABLE: extra turns all user-caused, task completed. INCOMPLETE: task did not complete, no bot error. FRICTION: bot-caused extra turn but task completed. BROKEN: bot error caused task failure.",
        },
        "task_completed": {
            "type": "boolean",
            "description": "True ONLY if the user's intended action completed with correct data. False if the bot logged wrong data, ignored a correction, or the conversation ended without achieving the goal. A bot message containing 'logged' does NOT make this true if the logged data was incorrect.",
        },
        "friction_turns": {
            "type": "array",
            "description": "One entry per turn beyond the first two. Empty array if conversation was 2 turns or fewer.",
            "items": {
                "type": "object",
                "description": "A single friction turn analysis.",
                "properties": {
                    "turn": {
                        "type": "integer",
                        "description": "The 1-based turn number in the conversation.",
                    },
                    "cause": {
                        "type": "string",
                        "enum": ["user", "bot"],
                        "description": "Who caused this extra turn. 'user' if the user failed to provide required info. 'bot' if the bot made an error that necessitated the extra turn. When the turn is tagged [image attached], default to 'user' unless there is explicit evidence of bot error visible in the conversation text.",
                    },
                    "description": {
                        "type": "string",
                        "description": "One sentence explaining why this turn was needed.",
                    },
                },
                "required": ["turn", "cause", "description"],
            },
        },
        "recovery_quality": {
            "type": "string",
            "enum": ["good", "partial", "failed", "not_needed"],
            "description": "How well the bot recovered after a user correction. 'good': corrected immediately. 'partial': fixed some but not all issues. 'failed': ignored correction or repeated error. 'not_needed': user never corrected the bot.",
        },
        "failure_reason": {
            "type": "string",
            "description": "If task_completed is false, one sentence stating the root cause of failure. If task_completed is true, this MUST be an empty string.",
        },
        "incomplete_reason": {
            "type": "string",
            "enum": ["user_inactive", "data_truncated", "user_chose_to_stop", ""],
            "description": "When verdict is INCOMPLETE, which sub-category applies: user_inactive (user simply did not respond), data_truncated (conversation cut off mid-flow), user_chose_to_stop (user explicitly stopped). Empty string for all other verdicts.",
        },
        "reasoning": {
            "type": "string",
            "description": "Two to three sentence assessment of the overall conversation quality, covering what went well and what went wrong.",
        },
        "rule_compliance": {
            "type": "array",
            "description": "One entry per production rule provided in the prompt. Every rule must be evaluated.",
            "items": {
                "type": "object",
                "description": "Compliance check for a single production rule.",
                "properties": {
                    "rule_id": {
                        "type": "string",
                        "description": "The exact rule_id as provided in the rules list.",
                    },
                    "status": {
                        "type": "string",
                        "enum": list(RULE_OUTCOME_STATUSES),
                        "description": "Canonical rule outcome status. FOLLOWED means the bot followed the rule, VIOLATED means it broke the rule, NOT_APPLICABLE means the rule did not apply, and NOT_EVALUATED means there was not enough evidence to conclude.",
                    },
                    "evidence": {
                        "type": "string",
                        "description": "One sentence citing specific turn(s) or bot behavior as evidence.",
                    },
                },
                "required": ["rule_id", "status", "evidence"],
            },
        },
    },
    "required": ["thread_type", "verdict", "task_completed", "friction_turns", "recovery_quality", "failure_reason", "incomplete_reason", "reasoning", "rule_compliance"],
}


class EfficiencyEvaluator:
    """Evaluates conversation efficiency and recovery (async)."""

    def __init__(
        self,
        llm_provider: BaseLLMProvider,
        rules: Optional[List[PromptRule]] = None,
    ):
        self.llm = llm_provider
        self.rules = list(rules) if rules is not None else get_rules_for_efficiency()

    async def evaluate_thread(self, thread: ConversationThread, thinking: str = "low", truncate_responses: bool = False) -> EfficiencyEvaluation:
        transcript = self._format_transcript(thread, truncate_responses=truncate_responses)
        rules_block = self._format_rules(self.rules)

        eval_prompt = (
            f"CONVERSATION THREAD: {thread.message_count} turns, {thread.duration_seconds:.0f} seconds\n\n"
            f"{transcript}\n\n"
            f"{rules_block}\n\n"
            "Evaluate this conversation. Produce a compliance entry for every rule listed above. "
            "Do not omit any rule. Do not invent rules not listed."
        )

        result = await self.llm.generate_json(
            prompt=eval_prompt,
            system_prompt=EFFICIENCY_JUDGE_SYSTEM_PROMPT,
            json_schema=EFFICIENCY_JSON_SCHEMA,
            thinking=thinking,
        )
        return self._parse_result(thread, result, self.rules)

    @staticmethod
    def _format_transcript(thread: ConversationThread, truncate_responses: bool = False) -> str:
        lines = []
        for i, msg in enumerate(thread.messages, 1):
            ts = msg.timestamp.strftime("%H:%M:%S")
            img_tag = " [image attached]" if msg.has_image else ""
            if truncate_responses and len(msg.final_response_message) > 1200:
                bot_resp = msg.final_response_message[:1200] + "..."
            else:
                bot_resp = msg.final_response_message
            lines.append(
                f"**Turn {i}** ({ts}) [{msg.intent_detected}/{msg.intent_query_type}]\n"
                f"  User: {msg.query_text}{img_tag}\n"
                f"  Bot: {bot_resp}"
            )
        return "\n\n".join(lines)

    @staticmethod
    def _format_rules(rules: List[PromptRule]) -> str:
        if not rules:
            return ""
        lines = [
            "PRODUCTION RULES TO EVALUATE",
            "You must include one rule_compliance entry for each rule below.\n",
        ]
        for i, r in enumerate(rules, 1):
            lines.append(f"{i}. {r.rule_id} [{r.section}]: {r.rule_text}")
        return "\n".join(lines)

    @staticmethod
    def _parse_rule_compliance(raw_compliance: list, rules: List[PromptRule]) -> List[RuleCompliance]:
        rule_map = {normalize_rule_id(r.rule_id): r for r in rules}
        compliance = []
        for item in raw_compliance:
            if not isinstance(item, dict):
                continue
            rid = normalize_rule_id(item.get("rule_id", ""))
            rule = rule_map.get(rid)
            if rule is None:
                logger.warning("Dropping unknown efficiency rule outcome: %s", rid or "<empty>")
                continue
            compliance.append(build_rule_compliance(
                rule_id=rid,
                section=rule.section,
                status=item.get("status"),
                followed=item.get("followed"),
                evidence=item.get("evidence", ""),
            ))
        returned_ids = {c.rule_id for c in compliance}
        for r in rules:
            if r.rule_id not in returned_ids:
                compliance.append(build_rule_compliance(
                    rule_id=r.rule_id,
                    section=r.section,
                    status="NOT_EVALUATED",
                    followed=None,
                    evidence="Not evaluated by judge",
                ))
        return compliance

    @staticmethod
    def _parse_result(thread: ConversationThread, raw: dict, rules: Optional[List[PromptRule]] = None) -> EfficiencyEvaluation:
        verdict = raw.get("verdict", "FRICTION")
        # Normalize NOT_APPLICABLE variants
        if verdict in ("NOT_APPLICABLE", "NOT APPLICABLE", "N/A"):
            verdict = "NOT APPLICABLE"
        elif verdict not in ("EFFICIENT", "ACCEPTABLE", "INCOMPLETE", "FRICTION", "BROKEN"):
            verdict = "FRICTION"

        rule_compliance = []
        if rules:
            rule_compliance = EfficiencyEvaluator._parse_rule_compliance(
                raw.get("rule_compliance", []), rules,
            )

        recovery_quality = raw.get("recovery_quality", "not needed").upper().replace("_", " ")
        friction_turns = raw.get("friction_turns", [])
        for ft in friction_turns:
            if "cause" in ft:
                ft["cause"] = ft["cause"].upper().replace("_", " ")

        # Safety net: reclassify bot-caused friction on image-bearing turns → user.
        # Image ambiguity originates with the user's choice to send a photo; the bot
        # cannot be blamed for vagueness that exists only because the image is absent
        # from the judge's context.
        image_turn_numbers = {
            i + 1
            for i, m in enumerate(thread.messages)
            if m.has_image
        }
        if image_turn_numbers:
            for ft in friction_turns:
                if ft.get("cause") == "BOT" and ft.get("turn") in image_turn_numbers:
                    ft["cause"] = "USER"
                    ft["description"] = (
                        f"[Image-based turn — friction reclassified from bot] "
                        f"{ft.get('description', '')}"
                    )

        # If the reclassification eliminated all bot-caused friction and the task
        # completed, upgrade FRICTION → ACCEPTABLE (mirrors correctness HARD_FAIL → PASS).
        if (
            verdict == "FRICTION"
            and raw.get("task_completed", False)
            and not any(ft.get("cause") == "BOT" for ft in friction_turns)
        ):
            verdict = "ACCEPTABLE"
            raw["reasoning"] = (
                f"[Image-based thread — bot-attributed friction reclassified to user after image context review] "
                f"{raw.get('reasoning', '')}"
            )

        # Resolve thread_type — default to meal_logging for backwards compat
        thread_type = raw.get("thread_type", "meal_logging")
        if thread_type not in ("meal_logging", "food_analysis", "cgm_query", "general", "greeting"):
            thread_type = "meal_logging"

        return EfficiencyEvaluation(
            thread=thread, verdict=verdict,
            task_completed=raw.get("task_completed", False),
            friction_turns=friction_turns,
            recovery_quality=recovery_quality,
            failure_reason=raw.get("failure_reason") or raw.get("abandonment_reason", ""),
            reasoning=raw.get("reasoning", ""),
            rule_compliance=rule_compliance,
            thread_type=thread_type,
            incomplete_reason=raw.get("incomplete_reason", ""),
        )
