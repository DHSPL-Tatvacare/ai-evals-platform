# Phase 3 — AI Narrative & Production Prompts

## Objective

Build the LLM-powered interpretation layer that takes aggregated metrics and produces structured narrative: executive summary, top issues, exemplar analysis, prompt gaps, and recommendations. Also move the Kaira production prompts into the platform as static constants.

## Pre-flight

- Branch: `feat/report-phase-3-narrative` from `main` (Phase 2 merged)
- LLM calls go through existing `llm_base.py` (`generate_json`)
- Model selection: use the same provider/model configured in the run's LLM settings

---

## Step 1: Production Prompt Constants

### `backend/app/services/reports/prompts/production_prompts.py`

Move content from the kaira-evals repo into static constants. These are **read-only, show-and-tell** — displayed in the prompt gap analysis section of the report so engineering can see what the production system uses.

```python
"""
Static production prompt constants for Kaira Bot.

These are the actual system prompts used in the production Kaira system.
They are stored here as reference material for the report's prompt gap
analysis — NOT used for evaluation. The evaluators have their own prompts.

Source: kaira-evals/prompts/KAIRA-INTENT-PROMPT.md
Source: kaira-evals/prompts/MEAL_SUMMARY_PROMPT_CONSTRUCTION.md
"""

# --- Intent Classification Prompt ---
# This is the system prompt used by Kaira's intent classification layer.
# It routes user messages to the appropriate agent (FoodAgent, CgmAgent, etc.)

KAIRA_INTENT_PROMPT = """<paste full content of KAIRA-INTENT-PROMPT.md>"""

# --- Meal Summary Prompt Construction ---
# This documents the conditional prompt construction logic for meal summaries.
# It's a specification document, not a single prompt — it describes 10+ conditional
# sections that get assembled based on runtime state.

KAIRA_MEAL_SUMMARY_SPEC = """<paste full content of MEAL_SUMMARY_PROMPT_CONSTRUCTION.md>"""
```

### Notes:
- These are multi-line string constants — keep the full content intact
- Add the source file path in a comment above each constant
- These files in the old `kaira-evals` repo can be deleted after this is confirmed working
- For future apps, add similar constants here (one file per app, or sections per app)

### App-aware accessor:
```python
def get_production_prompts(app_id: str) -> dict[str, str | None]:
    """Return production prompt constants for a given app."""
    if app_id == "kaira-bot":
        return {
            "intent_classification": KAIRA_INTENT_PROMPT,
            "meal_summary_spec": KAIRA_MEAL_SUMMARY_SPEC,
        }
    # Future: voice-rx, other apps
    return {
        "intent_classification": None,
        "meal_summary_spec": None,
    }
```

---

## Step 2: Narrative Prompt Templates

### `backend/app/services/reports/prompts/narrative_prompt.py`

The prompt sent to the LLM for narrative generation. This is the most critical prompt in the system — it must produce structured, actionable output.

```python
"""
Prompt templates for AI narrative generation.

The narrator LLM receives aggregated evaluation metrics and
must return a structured JSON response with analysis and recommendations.
"""

NARRATIVE_SYSTEM_PROMPT = """You are an AI evaluation analyst for a conversational health bot called Kaira.
Your task is to analyze evaluation results and produce a structured report for the engineering team.

You write in a direct, professional tone. No filler. Every sentence must be actionable or informative.
Use specific numbers from the data. Reference thread IDs when discussing examples.
Never fabricate data — only reference metrics and threads provided in the input.

Your output MUST be valid JSON matching the schema provided."""


def build_narrative_user_prompt(
    metadata: dict,
    health_score: dict,
    distributions: dict,
    rule_compliance: dict,
    friction: dict,
    adversarial: dict | None,
    exemplars: dict,
    production_prompts: dict,
) -> str:
    """
    Build the user prompt for narrative generation.

    This assembles ALL aggregated data into a single prompt so the LLM
    has the complete picture. The prompt is structured in sections to
    make it easy for the LLM to find relevant data for each output field.
    """

    sections = []

    # --- Section 1: Metadata ---
    sections.append(f"""## EVALUATION RUN METADATA
- App: {metadata.get('app_id', 'unknown')}
- Total threads: {metadata.get('total_threads', 0)}
- Completed: {metadata.get('completed_threads', 0)}
- Errors: {metadata.get('error_threads', 0)}
- Model: {metadata.get('llm_model', 'unknown')}
- Duration: {metadata.get('duration_ms', 0)}ms""")

    # --- Section 2: Health Score ---
    hs = health_score
    bd = hs.get('breakdown', {})
    sections.append(f"""## HEALTH SCORE: {hs.get('grade', '?')} ({hs.get('numeric', 0)}/100)
- Intent Accuracy: {bd.get('intent_accuracy', {}).get('value', 0)}% (weight 25%)
- Correctness Rate: {bd.get('correctness_rate', {}).get('value', 0)}% (weight 25%)
- Efficiency Rate: {bd.get('efficiency_rate', {}).get('value', 0)}% (weight 25%)
- Task Completion: {bd.get('task_completion', {}).get('value', 0)}% (weight 25%)""")

    # --- Section 3: Verdict Distributions ---
    sections.append(f"""## VERDICT DISTRIBUTIONS
Correctness: {_format_dict(distributions.get('correctness', {}))}
Efficiency: {_format_dict(distributions.get('efficiency', {}))}""")

    if adversarial:
        sections.append(f"""## ADVERSARIAL RESULTS
By category: {_format_adversarial_categories(adversarial.get('by_category', []))}
By difficulty: {_format_adversarial_difficulties(adversarial.get('by_difficulty', []))}""")

    # --- Section 4: Rule Compliance ---
    rules = rule_compliance.get('rules', [])
    rules_text = "\n".join([
        f"  - {r['rule_id']}: {r['passed']} pass / {r['failed']} fail "
        f"({r['rate']*100:.0f}%) [{r['severity']}]"
        for r in rules
    ])
    co_fails = rule_compliance.get('co_failures', [])
    co_text = "\n".join([
        f"  - {c['rule_a']} + {c['rule_b']}: co-fail rate {c['co_occurrence_rate']*100:.0f}%"
        for c in co_fails
    ])
    sections.append(f"""## RULE COMPLIANCE (sorted worst first)
{rules_text}

Co-failure pairs:
{co_text if co_text else '  None detected'}""")

    # --- Section 5: Friction ---
    fr = friction
    sections.append(f"""## FRICTION ANALYSIS
Total friction turns: {fr.get('total_friction_turns', 0)}
Bot-caused: {fr.get('by_cause', {}).get('bot', 0)}
User-caused: {fr.get('by_cause', {}).get('user', 0)}
Recovery quality: {_format_dict(fr.get('recovery_quality', {}))}
Avg turns by verdict: {_format_dict(fr.get('avg_turns_by_verdict', {}))}

Top friction patterns:
{_format_patterns(fr.get('top_patterns', []))}""")

    # --- Section 6: Exemplar Threads ---
    sections.append("## BEST THREADS (highest composite score)")
    for ex in exemplars.get('best', []):
        sections.append(_format_exemplar(ex, "GOOD"))

    sections.append("## WORST THREADS (lowest composite score)")
    for ex in exemplars.get('worst', []):
        sections.append(_format_exemplar(ex, "BAD"))

    # --- Section 7: Production Prompts (for gap analysis) ---
    if production_prompts.get('intent_classification'):
        sections.append(f"""## PRODUCTION PROMPT: INTENT CLASSIFICATION
{production_prompts['intent_classification'][:2000]}""")
    if production_prompts.get('meal_summary_spec'):
        sections.append(f"""## PRODUCTION PROMPT: MEAL SUMMARY SPEC (truncated)
{production_prompts['meal_summary_spec'][:3000]}""")

    # --- Instructions ---
    sections.append("""## YOUR TASK

Analyze the data above and return a JSON object with these fields:

1. **executive_summary** (string): 3-5 sentences summarizing overall quality.
   Include the health score grade, key strengths, and the #1 weakness.
   Be specific with numbers.

2. **top_issues** (array of 3-5 objects): Most impactful problems to fix.
   Each: {rank, area, description, affected_count, example_thread_id}
   - rank: 1-based priority
   - area: "correctness" | "efficiency" | "intent" | "adversarial"
   - description: One sentence, specific, actionable
   - affected_count: number of threads affected
   - example_thread_id: thread ID that best illustrates this issue

3. **exemplar_analysis** (array): For each best/worst thread, provide:
   {thread_id, type, what_happened, why, prompt_gap}
   - type: "good" | "bad"
   - what_happened: 2-3 sentences describing the interaction
   - why: Root cause (why it succeeded or failed)
   - prompt_gap: Which production prompt section is responsible (null if N/A)

4. **prompt_gaps** (array): Map rule failures to production prompt weaknesses.
   {prompt_section, eval_rule, gap_type, description, suggested_fix}
   - gap_type: "UNDERSPEC" (prompt doesn't cover case), "SILENT" (no guidance),
     "LEAKAGE" (allows unintended behavior), "CONFLICTING" (sections contradict)
   - suggested_fix: Specific text change to the production prompt
   Only include gaps where you can identify a clear prompt section and rule link.

5. **recommendations** (array of 3-7): Prioritized engineering actions.
   {priority, area, action, estimated_impact}
   - priority: "P0" (critical), "P1" (high), "P2" (medium)
   - action: Specific, implementable instruction (not vague)
   - estimated_impact: e.g. "-12 failures", "-6 friction turns"
   Base impact estimates on affected_count from the data. Be conservative.

IMPORTANT:
- Only reference thread IDs that exist in the data above
- Only reference rules that appear in the rule compliance section
- Base all numbers on the actual data — do not estimate or round
- If production prompts are not provided, skip the prompt_gaps section (empty array)
- Keep total response under 3000 tokens""")

    return "\n\n".join(sections)


# --- Helper formatters ---

def _format_dict(d: dict) -> str:
    return ", ".join(f"{k}: {v}" for k, v in d.items())

def _format_patterns(patterns: list) -> str:
    if not patterns:
        return "  None detected"
    return "\n".join([
        f"  {i+1}. \"{p.get('description', '')}\" ({p.get('count', 0)} occurrences, "
        f"threads: {', '.join(p.get('example_thread_ids', [])[:2])})"
        for i, p in enumerate(patterns)
    ])

def _format_exemplar(ex: dict, label: str) -> str:
    transcript = ex.get('transcript', [])
    transcript_text = "\n".join([
        f"  [{m.get('role', '?').upper()}]: {m.get('content', '')[:200]}"
        for m in transcript[:6]  # max 6 messages to keep prompt size reasonable
    ])
    violations = ex.get('rule_violations', [])
    violations_text = ", ".join([v.get('rule_id', '') for v in violations]) or "none"

    return f"""### {label}: Thread {ex.get('thread_id', '?')} (score: {ex.get('composite_score', 0):.2f})
Verdicts: correctness={ex.get('correctness_verdict', '?')}, efficiency={ex.get('efficiency_verdict', '?')}, intent={ex.get('intent_accuracy', '?')}, task_completed={ex.get('task_completed', '?')}
Rule violations: {violations_text}
Transcript:
{transcript_text}"""

def _format_adversarial_categories(cats: list) -> str:
    return ", ".join([
        f"{c.get('category', '?')}: {c.get('passed', 0)}/{c.get('total', 0)}"
        for c in cats
    ])

def _format_adversarial_difficulties(diffs: list) -> str:
    return ", ".join([
        f"{d.get('difficulty', '?')}: {d.get('passed', 0)}/{d.get('total', 0)}"
        for d in diffs
    ])
```

---

## Step 3: Narrator Service

### `backend/app/services/reports/narrator.py`

```python
"""
AI narrative generator.

Takes aggregated report data, calls LLM, returns structured NarrativeOutput.
Uses existing llm_base.py abstraction — same provider/model as evaluation runs.
"""

import logging
from app.services.evaluators.llm_base import BaseLLMProvider
from app.services.evaluators.settings_helper import get_llm_provider
from app.services.reports.schemas import NarrativeOutput
from app.services.reports.prompts.narrative_prompt import (
    NARRATIVE_SYSTEM_PROMPT,
    build_narrative_user_prompt,
)

logger = logging.getLogger(__name__)

# JSON schema for structured output
NARRATIVE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "executive_summary": {"type": "string"},
        "top_issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rank": {"type": "integer"},
                    "area": {"type": "string"},
                    "description": {"type": "string"},
                    "affected_count": {"type": "integer"},
                    "example_thread_id": {"type": ["string", "null"]},
                },
                "required": ["rank", "area", "description", "affected_count"],
            },
        },
        "exemplar_analysis": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string"},
                    "type": {"type": "string", "enum": ["good", "bad"]},
                    "what_happened": {"type": "string"},
                    "why": {"type": "string"},
                    "prompt_gap": {"type": ["string", "null"]},
                },
                "required": ["thread_id", "type", "what_happened", "why"],
            },
        },
        "prompt_gaps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "prompt_section": {"type": "string"},
                    "eval_rule": {"type": "string"},
                    "gap_type": {"type": "string", "enum": ["UNDERSPEC", "SILENT", "LEAKAGE", "CONFLICTING"]},
                    "description": {"type": "string"},
                    "suggested_fix": {"type": "string"},
                },
                "required": ["prompt_section", "eval_rule", "gap_type", "description", "suggested_fix"],
            },
        },
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "priority": {"type": "string", "enum": ["P0", "P1", "P2"]},
                    "area": {"type": "string"},
                    "action": {"type": "string"},
                    "estimated_impact": {"type": "string"},
                },
                "required": ["priority", "area", "action", "estimated_impact"],
            },
        },
    },
    "required": ["executive_summary", "top_issues", "exemplar_analysis", "prompt_gaps", "recommendations"],
}


class ReportNarrator:
    """
    Generates AI narrative from aggregated report data.

    Uses the same LLM provider configured for the app's evaluations.
    Falls back gracefully if LLM call fails — report still works without narrative.
    """

    def __init__(self, provider: BaseLLMProvider):
        self.provider = provider

    async def generate(
        self,
        metadata: dict,
        health_score: dict,
        distributions: dict,
        rule_compliance: dict,
        friction: dict,
        adversarial: dict | None,
        exemplars: dict,
        production_prompts: dict,
    ) -> NarrativeOutput | None:
        """
        Generate narrative. Returns None on failure (report still valid without it).
        """
        try:
            user_prompt = build_narrative_user_prompt(
                metadata=metadata,
                health_score=health_score,
                distributions=distributions,
                rule_compliance=rule_compliance,
                friction=friction,
                adversarial=adversarial,
                exemplars=exemplars,
                production_prompts=production_prompts,
            )

            result = await self.provider.generate_json(
                prompt=user_prompt,
                system_prompt=NARRATIVE_SYSTEM_PROMPT,
                json_schema=NARRATIVE_JSON_SCHEMA,
            )

            return NarrativeOutput(
                executive_summary=result.get("executive_summary", ""),
                top_issues=[
                    TopIssue(**issue) for issue in result.get("top_issues", [])
                ],
                exemplar_analysis=[
                    ExemplarAnalysis(**ea) for ea in result.get("exemplar_analysis", [])
                ],
                prompt_gaps=[
                    PromptGap(**pg) for pg in result.get("prompt_gaps", [])
                ],
                recommendations=[
                    Recommendation(**rec) for rec in result.get("recommendations", [])
                ],
            )

        except Exception as e:
            logger.error(f"Report narrative generation failed: {e}", exc_info=True)
            return None
```

### Key design decisions:
- **Graceful failure**: If LLM call fails, returns `None` — the report still has all computed data, just no AI narrative. Frontend shows a "Narrative unavailable" message.
- **Provider reuse**: Uses the same `BaseLLMProvider` that evaluators use. Provider is instantiated by the service layer using `get_llm_provider()`.
- **JSON schema**: Full schema enforced via `generate_json()` — same pattern as correctness/efficiency evaluators.
- **Prompt size management**: Transcripts are truncated to 6 messages × 200 chars, production prompts capped at 2000/3000 chars. Total prompt stays under ~8K tokens.

---

## Step 4: Wire Narrator into ReportService

Update `report_service.py`:

```python
from .narrator import ReportNarrator
from .prompts.production_prompts import get_production_prompts
from app.services.evaluators.settings_helper import get_llm_provider


async def generate(self, run_id: str) -> ReportPayload:
    run = await self._load_run(run_id)
    threads = await self._load_threads(run_id)
    adversarial_rows = await self._load_adversarial(run_id)

    # Health score
    summary = run.summary or {}
    health_score = compute_health_score(...)

    # Aggregate
    agg = ReportAggregator(threads, adversarial_rows, summary, run.batch_metadata)
    distributions = agg.compute_distributions()
    rule_compliance = agg.compute_rule_compliance()
    friction = agg.compute_friction_analysis()
    exemplars = agg.select_exemplars(k=5)
    adversarial_breakdown = agg.compute_adversarial_breakdown()

    # Metadata
    metadata = self._build_metadata(run, threads, adversarial_rows)

    # Production prompts
    prod_prompts = get_production_prompts(run.app_id)
    production_prompts = ProductionPrompts(
        intent_classification=prod_prompts.get("intent_classification"),
        meal_summary_spec=prod_prompts.get("meal_summary_spec"),
    )

    # AI Narrative (non-blocking — failure is OK)
    narrative = None
    try:
        provider = await get_llm_provider(self.db, run.app_id)
        narrator = ReportNarrator(provider)
        narrative = await narrator.generate(
            metadata=metadata.model_dump(),
            health_score=health_score.model_dump(),
            distributions=distributions.model_dump(),
            rule_compliance=rule_compliance.model_dump(),
            friction=friction.model_dump(),
            adversarial=adversarial_breakdown.model_dump() if adversarial_breakdown else None,
            exemplars=exemplars.model_dump(),
            production_prompts=prod_prompts,
        )
    except Exception as e:
        logger.warning(f"Narrative generation skipped: {e}")

    return ReportPayload(
        metadata=metadata,
        health_score=health_score,
        distributions=distributions,
        rule_compliance=rule_compliance,
        friction=friction,
        adversarial=adversarial_breakdown,
        exemplars=exemplars,
        production_prompts=production_prompts,
        narrative=narrative,
    )
```

### Provider instantiation:
- `get_llm_provider(db, app_id)` already exists in `settings_helper.py` — it reads LLM settings from the DB and returns a configured `GeminiProvider` or `OpenAIProvider`
- If settings don't exist, it raises an error — caught by the try/except, narrative becomes None

---

## Step 5: Prompt Token Budget

Estimate token usage for the narrative LLM call:

| Section | Est. Tokens |
|---------|-------------|
| System prompt | ~150 |
| Metadata | ~100 |
| Health score | ~100 |
| Distributions | ~200 |
| Rule compliance (13 rules) | ~400 |
| Friction analysis | ~300 |
| Adversarial (if present) | ~200 |
| Best 5 exemplars (6 msgs × 200 chars each) | ~2000 |
| Worst 5 exemplars | ~2000 |
| Production prompts (truncated) | ~2000 |
| Instructions | ~500 |
| **Total input** | **~8000** |
| **Expected output** | **~2000-3000** |
| **Total** | **~11000** |

This fits comfortably within Gemini Flash context (1M) and even GPT-4o-mini (128K). Cost per report: ~$0.01-0.03 with Flash.

---

## Verification Checklist

- [ ] Production prompt constants compile and contain full content from source files
- [ ] `get_production_prompts("kaira-bot")` returns both prompts
- [ ] `get_production_prompts("voice-rx")` returns nulls (graceful for other apps)
- [ ] Narrator prompt builds without errors for a real run's data
- [ ] `generate_json` call succeeds and returns valid structured output
- [ ] Narrative fields are populated in the ReportPayload response
- [ ] If LLM call fails (e.g., bad API key), report still returns with `narrative: null`
- [ ] Prompt stays under ~10K tokens for a typical 20-thread run
- [ ] No production prompt content leaks into evaluator prompts (complete separation)
- [ ] Source files from `kaira-evals/prompts/` can be referenced for verification

## Notes on Future Apps

- To add reports for `voice-rx`: add production prompt constants, extend `get_production_prompts()`
- The narrator prompt is app-aware via metadata.app_id — it describes itself as analyzing "Kaira" or "Voice Rx" based on this
- The NARRATIVE_SYSTEM_PROMPT may need per-app customization eventually (different domain context). For now, the generic version works because the data itself carries the domain context.
