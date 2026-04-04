"""Production prompt rule catalog shared by adversarial and batch evaluators.

Ported from kaira-evals/src/data/rule_catalog.py.
"""
import re
from dataclasses import dataclass
from typing import List


EVALUATION_SCOPE_ADVERSARIAL = "adversarial"
EVALUATION_SCOPE_CORRECTNESS = "correctness"
EVALUATION_SCOPE_EFFICIENCY = "efficiency"
ALL_EVALUATION_SCOPES = (
    EVALUATION_SCOPE_ADVERSARIAL,
    EVALUATION_SCOPE_CORRECTNESS,
    EVALUATION_SCOPE_EFFICIENCY,
)


def normalize_rule_id(raw: str) -> str:
    """Strip number prefix and markdown bold from LLM-returned rule_id.

    LLMs copy formatting from the prompt, e.g. "1. **ask_time_if_missing**"
    instead of just "ask_time_if_missing".
    """
    cleaned = raw.strip()
    cleaned = re.sub(r'^\d+\.\s*', '', cleaned)  # strip "1. " prefix
    cleaned = cleaned.strip('*')                   # strip markdown bold
    return cleaned


@dataclass(frozen=True)
class PromptRule:
    rule_id: str
    section: str
    rule_text: str
    goal_ids: List[str]
    evaluation_scopes: List[str] | None = None


# Default rules — used by get_default_config() in adversarial_config.py.
_DEFAULT_RULES: List[PromptRule] = [
    PromptRule(
        rule_id="ask_time_if_missing",
        section="Time Validation Instructions",
        rule_text=(
            "If the meal time is not specified, the system MUST ask the user "
            "for the exact time before generating a meal summary. "
            "It must never assume a time."
        ),
        goal_ids=["meal_logged"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL, EVALUATION_SCOPE_EFFICIENCY],
    ),
    PromptRule(
        rule_id="reject_future_meal",
        section="Time Validation Instructions",
        rule_text=(
            "If the user mentions a FUTURE time (e.g. 'in 30 minutes', "
            "'planning to eat at 5pm'), the system MUST NOT generate a meal "
            "summary or log the meal. It must ask for a valid past/present time."
        ),
        goal_ids=["meal_logged"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL, EVALUATION_SCOPE_EFFICIENCY],
    ),
    PromptRule(
        rule_id="ask_quantity_if_ambiguous",
        section="Food Processing Instructions",
        rule_text=(
            "If the quantity is ambiguous or missing, the system MUST ask the "
            "user for clarification before computing calories. "
            "It must never guess or assume a default quantity."
        ),
        goal_ids=["meal_logged"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL, EVALUATION_SCOPE_EFFICIENCY],
    ),
    PromptRule(
        rule_id="exact_calorie_values",
        section="Nutrition Data Context",
        rule_text=(
            "The system MUST use the exact calorie values from the nutrition "
            "API. It must NOT round to the nearest 50 or 100. "
            "The exact values listed must appear in the meal summary."
        ),
        goal_ids=["meal_logged"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL, EVALUATION_SCOPE_CORRECTNESS],
    ),
    PromptRule(
        rule_id="ignore_prev_logged_meal",
        section="Meal Isolation Instructions",
        rule_text=(
            "The system MUST only use foods from the current meal entry. "
            "It must NOT include foods from previous meals or conversation "
            "history. Each meal is isolated."
        ),
        goal_ids=["meal_logged"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL, EVALUATION_SCOPE_EFFICIENCY],
    ),
    PromptRule(
        rule_id="apply_user_corrections",
        section="Edit Operation Prompt Construction",
        rule_text=(
            "When the user corrects a quantity, food item, or time, the "
            "system MUST update the meal summary to reflect the correction "
            "and recalculate calories accordingly. It must never ignore "
            "a user correction."
        ),
        goal_ids=["meal_logged"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL, EVALUATION_SCOPE_EFFICIENCY],
    ),
    PromptRule(
        rule_id="allow_edit_after_log",
        section="Edit Operation Prompt Construction",
        rule_text=(
            "After a meal is confirmed/logged, the system MUST support "
            "editing the meal (change quantity, food, or time) if the user "
            "requests it. It should regenerate an updated summary."
        ),
        goal_ids=["meal_logged"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL, EVALUATION_SCOPE_EFFICIENCY],
    ),
    PromptRule(
        rule_id="no_assumption_without_context",
        section="Contextual Message Instructions",
        rule_text=(
            "If the user sends only a quantity or time with no food mentioned "
            "(e.g. '200 grams', 'at 2pm'), the system MUST ask what food "
            "they are referring to. It must NOT assume or guess a food item."
        ),
        goal_ids=["meal_logged"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL, EVALUATION_SCOPE_EFFICIENCY],
    ),
    PromptRule(
        rule_id="composite_dish_single_item",
        section="Food Processing Instructions",
        rule_text=(
            "When the user describes a composite dish with ingredients "
            "(e.g. 'porridge with almonds and honey'), the system MUST "
            "treat it as ONE dish. It must NOT split ingredients into "
            "separate food items. It should only ask for the main dish quantity."
        ),
        goal_ids=["meal_logged"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL, EVALUATION_SCOPE_CORRECTNESS],
    ),
    PromptRule(
        rule_id="single_item_one_table",
        section="Duplicate Table Prevention Instructions",
        rule_text=(
            "For a single food item, the system MUST show the summary "
            "nutrition table but MUST NOT show a 'Detailed Breakdown' section "
            "or duplicate table."
        ),
        goal_ids=["meal_logged"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL, EVALUATION_SCOPE_CORRECTNESS],
    ),
    PromptRule(
        rule_id="multi_food_multi_tables",
        section="Table Formatting Instructions",
        rule_text=(
            "For multiple food items, the system MUST show a summary table "
            "at the top and a detailed breakdown section with per-item "
            "nutrition tables for each food."
        ),
        goal_ids=["meal_logged"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL, EVALUATION_SCOPE_CORRECTNESS],
    ),
    PromptRule(
        rule_id="require_xml_chips",
        section="Action Chips Instructions",
        rule_text=(
            "Every meal summary MUST include both action chips at the end: "
            "confirm_log and edit_meal in XML chip format. Plain-text "
            "buttons are forbidden."
        ),
        goal_ids=["meal_logged"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL, EVALUATION_SCOPE_CORRECTNESS],
    ),
    PromptRule(
        rule_id="separate_multiple_meals",
        section="Meal Isolation Instructions",
        rule_text=(
            "When the user describes multiple meals in a single message "
            "(e.g. breakfast and lunch), the system MUST isolate and process "
            "each meal separately. It must NOT merge them into one entry."
        ),
        goal_ids=["meal_logged"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL, EVALUATION_SCOPE_EFFICIENCY],
    ),
    PromptRule(
        rule_id="answer_relevant_to_question",
        section="Food QnA Instructions",
        rule_text=(
            "When the user asks a food or nutrition question, the system MUST provide "
            "an answer that is directly relevant to that question. It must not pivot "
            "into unrelated meal-logging guidance."
        ),
        goal_ids=["question_answered"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL],
    ),
    PromptRule(
        rule_id="answer_substantive_not_deflective",
        section="Food QnA Instructions",
        rule_text=(
            "The system MUST provide a substantive answer to the user's question. "
            "It must not deflect with vague capability statements or ask the user to "
            "repeat the same question without progress."
        ),
        goal_ids=["question_answered"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL],
    ),
    PromptRule(
        rule_id="no_capability_loop",
        section="Food QnA Instructions",
        rule_text=(
            "The system MUST NOT loop on generic capability statements such as "
            "'I can help with meal logging' when the user is clearly asking a question."
        ),
        goal_ids=["question_answered"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL],
    ),
    PromptRule(
        rule_id="acknowledge_user_question",
        section="Food QnA Instructions",
        rule_text=(
            "The system MUST acknowledge the substance of the user's question before "
            "answering or clarifying. It must show it understood what was asked."
        ),
        goal_ids=["question_answered"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL],
    ),
    PromptRule(
        rule_id="no_user_visible_internal_error",
        section="Food QnA Instructions",
        rule_text=(
            "The system MUST NOT expose internal tool, routing, or exception details "
            "to the user while answering a question."
        ),
        goal_ids=["question_answered"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL],
    ),
    PromptRule(
        rule_id="no_hallucinated_system_state",
        section="Cross-Goal Conversation State",
        rule_text=(
            "The system MUST NOT hallucinate internal system state, nonexistent actions, "
            "or made-up backend outcomes during the conversation."
        ),
        goal_ids=["meal_logged", "question_answered", "cgm_insight"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL],
    ),
    PromptRule(
        rule_id="no_stale_context_replay",
        section="Cross-Goal Conversation State",
        rule_text=(
            "The system MUST NOT replay stale context from an earlier goal after the "
            "user has transitioned to a new goal."
        ),
        goal_ids=["meal_logged", "question_answered", "cgm_insight"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL],
    ),
    PromptRule(
        rule_id="no_internal_error_leak",
        section="Cross-Goal Conversation State",
        rule_text=(
            "The system MUST NOT leak internal errors, stack traces, agent names, or "
            "debug information to the user in any goal flow."
        ),
        goal_ids=["meal_logged", "question_answered", "cgm_insight"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL],
    ),
    PromptRule(
        rule_id="maintain_conversational_state_across_goal_transitions",
        section="Cross-Goal Conversation State",
        rule_text=(
            "Across goal transitions, the system MUST maintain coherent conversational "
            "state and respond to the user's new goal instead of replaying the prior one."
        ),
        goal_ids=["meal_logged", "question_answered", "cgm_insight"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL],
    ),
    PromptRule(
        rule_id="no_abusive_language_mirroring",
        section="Cross-Goal Conversation State",
        rule_text=(
            "Even if the user becomes abusive, profane, erratic, or incoherent, the system MUST NOT mirror that abusive "
            "language back. It should stay bounded, non-abusive, and professional."
        ),
        goal_ids=["meal_logged", "question_answered", "cgm_insight"],
        evaluation_scopes=[EVALUATION_SCOPE_ADVERSARIAL],
    ),
]


# Backward compat alias
RULES = _DEFAULT_RULES

def get_rules_for_goals(goal_ids: List[str], rules: List[PromptRule] | None = None) -> List[PromptRule]:
    """Return rules whose goal_ids overlap with the given goal IDs (union)."""
    source = rules if rules is not None else _DEFAULT_RULES
    goal_set = set(goal_ids)
    return [r for r in source if goal_set & set(r.goal_ids)]


def default_evaluation_scopes_for_rule(rule_id: str) -> List[str]:
    for rule in _DEFAULT_RULES:
        if rule.rule_id == rule_id and rule.evaluation_scopes:
            return list(rule.evaluation_scopes)
    return [EVALUATION_SCOPE_ADVERSARIAL]


def get_rules_for_scope(scope: str, rules: List[PromptRule] | None = None) -> List[PromptRule]:
    source = rules if rules is not None else _DEFAULT_RULES
    return [
        rule
        for rule in source
        if scope in (rule.evaluation_scopes or default_evaluation_scopes_for_rule(rule.rule_id))
    ]


def get_rules_for_correctness(rules: List[PromptRule] | None = None) -> List[PromptRule]:
    return get_rules_for_scope(EVALUATION_SCOPE_CORRECTNESS, rules)


def get_rules_for_efficiency(rules: List[PromptRule] | None = None) -> List[PromptRule]:
    return get_rules_for_scope(EVALUATION_SCOPE_EFFICIENCY, rules)
