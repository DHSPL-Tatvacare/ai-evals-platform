# Phase 1: Evaluator Definitions

All 4 evaluators follow the identical structure as the existing kaira-bot evaluators in `KAIRA_BOT_EVALUATORS`. Each is a dict with: `app_id`, `name`, `is_global`, `listing_id`, `show_in_header`, `prompt`, `output_schema`.

The `{{chat_transcript}}` variable resolves to the existing `format_chat_transcript()` output — lines of `User: ...` and `Bot: ...` from the chat session messages. The LLM judge reads ONLY this transcript.

---

## Evaluator 1: Domain Routing Accuracy

**Purpose:** Detects when the bot responds in the wrong domain. Grounded in the context-switcher's agent taxonomy: FoodAgent (food logging), FoodInsightAgent (food analysis), CgmAgent (glucose/CGM), General.

**What the LLM judge looks for in the transcript:**
- User asks about glucose → bot should respond with glucose data, not food logging prompts
- User says "I had pizza" → bot should initiate food logging, not answer a CGM question
- User asks "which meals spiked my glucose" → bot should provide a mixed CGM+food answer, not just one domain
- User switches topics mid-conversation → bot should follow the switch, not continue the previous domain

**Prompt:**

```
You are a domain routing evaluator for a health assistant that handles three domains:
- FOOD LOGGING: Recording what the user ate (statements like "I had pizza", "I ate rice")
- FOOD ANALYSIS: Answering questions about logged food data, nutrition trends, calorie goals
- CGM/GLUCOSE: Answering questions about glucose levels, spikes, blood sugar patterns, CGM data
- GENERAL: Health questions not specific to the above domains

═══════════════════════════════════════════════════════════════════════════════
CHAT TRANSCRIPT
═══════════════════════════════════════════════════════════════════════════════

{{chat_transcript}}

═══════════════════════════════════════════════════════════════════════════════
EVALUATION TASK
═══════════════════════════════════════════════════════════════════════════════

For EACH user message in the transcript, determine:

1. WHAT DOMAIN does the user's message belong to? (Food Logging / Food Analysis / CGM-Glucose / General / Mixed)
2. DID THE BOT RESPOND IN THE CORRECT DOMAIN?
   - A correct response addresses the domain the user asked about
   - A wrong-domain response talks about something the user did not ask about
   - For mixed queries (e.g. "which meals spiked my glucose"), the bot must address BOTH domains

3. IF THE USER SWITCHED TOPICS between turns, did the bot follow the switch or continue in the old domain?

SCORING:
- Count each user-bot exchange as one turn
- A turn is "correctly routed" if the bot's response addresses the domain the user asked about
- routing_accuracy = (correctly routed turns / total turns) * 100

DO NOT penalize for:
- Quality of the response (that is judged by other evaluators)
- Minor tangents if the core domain is correct
- Greetings or small talk

DO penalize for:
- Bot answering about food when user asked about glucose (or vice versa)
- Bot continuing food logging flow when user clearly switched to a glucose question
- Bot ignoring one side of a mixed-domain question entirely

Output structure is controlled by the schema - just provide the data.
```

**Output Schema:**

```python
[
    {
        "key": "routing_accuracy",
        "type": "number",
        "description": "Percentage of user-bot turns where the bot responded in the correct domain (0-100)",
        "displayMode": "header",
        "isMainMetric": True,
        "thresholds": {"green": 90, "yellow": 70},
    },
    {
        "key": "total_turns",
        "type": "number",
        "description": "Total number of user-bot exchanges evaluated",
        "displayMode": "card",
        "isMainMetric": False,
    },
    {
        "key": "misrouted_turns",
        "type": "number",
        "description": "Number of turns where the bot responded in the wrong domain",
        "displayMode": "card",
        "isMainMetric": False,
    },
    {
        "key": "analysis",
        "type": "text",
        "description": "Per-turn domain classification and routing assessment",
        "displayMode": "hidden",
        "isMainMetric": False,
        "role": "reasoning",
    },
]
```

**`show_in_header`: True** — routing errors are critical visibility items.

---

## Evaluator 2: Data Faithfulness

**Purpose:** Detects when the bot presents numbers, dates, or facts that are internally inconsistent within the conversation, or makes claims not grounded in data it showed the user. This is NOT about whether the underlying data source is correct — it is about whether the bot's prose matches the data the bot itself presented.

**What the LLM judge looks for in the transcript:**
- Bot says "your glucose peaked at 180 mg/dL" in one turn, then says "your highest reading was 165" in another → contradiction
- Bot presents a table of glucose readings then summarizes with numbers that don't match the table
- Bot says "you had 3 spikes this week" but the data it showed lists 5 spikes
- Bot makes a specific claim ("your carb intake was highest on Monday") without having shown the underlying data

**Prompt:**

```
You are a data faithfulness evaluator for a health assistant. Your job is to check whether the bot's statements are consistent with the data it presents within the conversation.

═══════════════════════════════════════════════════════════════════════════════
CHAT TRANSCRIPT
═══════════════════════════════════════════════════════════════════════════════

{{chat_transcript}}

═══════════════════════════════════════════════════════════════════════════════
EVALUATION TASK
═══════════════════════════════════════════════════════════════════════════════

You are checking INTERNAL CONSISTENCY — whether the bot's own words match the data the bot itself presented. You are NOT verifying against an external ground truth.

For each bot response that contains specific data (numbers, dates, rankings, counts, comparisons):

1. IDENTIFY every concrete claim the bot makes:
   - Specific numbers (glucose values, calorie counts, percentages)
   - Rankings or comparisons ("highest", "most", "better than")
   - Counts ("3 spikes", "5 meals")
   - Time references ("on Monday", "this week", "at 2pm")

2. CHECK each claim against:
   - Data tables, lists, or values the bot presented in the SAME response
   - Data the bot presented in PREVIOUS responses in this conversation
   - Other claims the bot made (cross-turn consistency)

3. FLAG any instance where:
   - A number in the bot's summary doesn't match numbers in its own table/list
   - The bot contradicts something it said in a previous turn
   - The bot makes a specific claim without having shown supporting data
   - The bot's ranking/comparison doesn't match the data it showed

SEVERITY:
- CRITICAL: Numerical contradictions (bot says X in one place and Y in another for the same metric)
- MODERATE: Unsupported claims (bot asserts something specific without showing data)
- MINOR: Imprecise summaries (bot says "about 150" when data shows 148)

SCORING:
- faithfulness_score: 1-10 scale
  10 = Every claim is perfectly supported by presented data, no contradictions
  7-9 = Minor imprecisions but no real contradictions
  4-6 = Some unsupported claims or a moderate inconsistency
  1-3 = Clear numerical contradictions or fabricated data points

If the conversation contains no data-bearing responses (e.g. only greetings), score 10 and note "no data claims to verify" in the analysis.

Output structure is controlled by the schema - just provide the data.
```

**Output Schema:**

```python
[
    {
        "key": "faithfulness_score",
        "type": "number",
        "description": "Data faithfulness score — internal consistency of bot's claims with its own presented data (1-10)",
        "displayMode": "header",
        "isMainMetric": True,
        "thresholds": {"green": 8, "yellow": 5},
    },
    {
        "key": "claims_checked",
        "type": "number",
        "description": "Total number of concrete data claims identified and verified",
        "displayMode": "card",
        "isMainMetric": False,
    },
    {
        "key": "inconsistencies_found",
        "type": "number",
        "description": "Number of contradictions or unsupported claims detected",
        "displayMode": "card",
        "isMainMetric": False,
    },
    {
        "key": "analysis",
        "type": "text",
        "description": "Per-claim faithfulness assessment with severity classifications",
        "displayMode": "hidden",
        "isMainMetric": False,
        "role": "reasoning",
    },
]
```

**`show_in_header`: True** — data faithfulness is a critical trust metric.

---

## Evaluator 3: CGM-Food Correlation Quality

**Purpose:** For conversations where the user asks questions that span both glucose AND food data, checks whether the bot actually correlated the two datasets in its answer or only addressed one side.

**What the LLM judge looks for in the transcript:**
- User asks "which meals caused my glucose spikes" → bot should mention specific meals AND their glucose impact together
- User asks "how does my diet affect my blood sugar" → bot should connect food items to glucose patterns
- If the user only asks about food OR only about glucose (not both), this evaluator should score N/A / full marks

**Prompt:**

```
You are a correlation quality evaluator for a health assistant that can access both CGM (Continuous Glucose Monitor) data and food/meal logs.

═══════════════════════════════════════════════════════════════════════════════
CHAT TRANSCRIPT
═══════════════════════════════════════════════════════════════════════════════

{{chat_transcript}}

═══════════════════════════════════════════════════════════════════════════════
EVALUATION TASK
═══════════════════════════════════════════════════════════════════════════════

STEP 1: Identify if any user message in the transcript asks a CROSS-DOMAIN question — one that requires connecting glucose/CGM data with food/meal data to answer properly.

Examples of cross-domain questions:
- "Which meals caused my glucose spikes?"
- "How does my diet affect my blood sugar?"
- "What did I eat before that spike?"
- "Which foods keep my glucose stable?"
- "Did my glucose go up after lunch?"
- "How soon after eating does my glucose rise?"

Examples of SINGLE-domain questions (NOT cross-domain):
- "What's my glucose level?" (CGM only)
- "What did I eat today?" (Food only)
- "I had pizza" (Food logging only)
- "Show my glucose stats for this week" (CGM only)

STEP 2: If NO cross-domain questions exist, set has_cross_domain_query to false, correlation_score to 10, and explain in analysis that this conversation had no cross-domain questions to evaluate.

STEP 3: If cross-domain questions DO exist, evaluate EACH one:

For each cross-domain question, check the bot's response for:

A. FOOD SIDE PRESENT? Does the response mention specific foods, meals, or dietary data?
B. GLUCOSE SIDE PRESENT? Does the response mention specific glucose values, spikes, ranges, or patterns?
C. ACTUAL CORRELATION? Does the response explicitly connect the two — e.g., "after your lunch of rice and dal, your glucose peaked at 180 mg/dL" — rather than listing food data and glucose data separately without connecting them?
D. TEMPORAL ALIGNMENT? When correlating, does the response match meals to glucose readings from the same time period?

SCORING:
- correlation_score: 1-10 scale
  10 = Cross-domain questions fully answered with explicit food-glucose connections
  7-9 = Both data types present, some correlation attempted but could be more explicit
  4-6 = Both data types present but listed separately without meaningful connection
  1-3 = Only one side addressed, the other ignored entirely

Output structure is controlled by the schema - just provide the data.
```

**Output Schema:**

```python
[
    {
        "key": "correlation_score",
        "type": "number",
        "description": "Quality of food-glucose correlation in cross-domain answers (1-10, or 10 if no cross-domain questions)",
        "displayMode": "header",
        "isMainMetric": True,
        "thresholds": {"green": 8, "yellow": 5},
    },
    {
        "key": "has_cross_domain_query",
        "type": "boolean",
        "description": "Whether the conversation contains questions requiring both food and glucose data",
        "displayMode": "card",
        "isMainMetric": False,
    },
    {
        "key": "cross_domain_questions_found",
        "type": "number",
        "description": "Number of cross-domain questions identified in the conversation",
        "displayMode": "card",
        "isMainMetric": False,
    },
    {
        "key": "analysis",
        "type": "text",
        "description": "Per-question correlation assessment — what food and glucose data was presented and how they were connected",
        "displayMode": "hidden",
        "isMainMetric": False,
        "role": "reasoning",
    },
]
```

**`show_in_header`: False** — only relevant for cross-domain conversations, not every chat.

---

## Evaluator 4: Date Handling Accuracy

**Purpose:** Checks whether the bot responded with data for the time period the user actually asked about. If the user asked about "last week" and the bot returned today's data, that's a date handling failure — visible in the transcript without needing to see internal tool calls.

**What the LLM judge looks for in the transcript:**
- User says "September glucose data" → bot's response should reference September dates, not October
- User says "last week" → bot's data should span the previous 7 days, not today only
- User says "yesterday's meals" → bot should show yesterday's data, not today's
- Bot presents a table with date columns → dates should fall within the requested range

**Prompt:**

```
You are a date handling evaluator for a health assistant that retrieves time-series glucose data and daily food logs.

═══════════════════════════════════════════════════════════════════════════════
CHAT TRANSCRIPT
═══════════════════════════════════════════════════════════════════════════════

{{chat_transcript}}

═══════════════════════════════════════════════════════════════════════════════
EVALUATION TASK
═══════════════════════════════════════════════════════════════════════════════

STEP 1: For each user message, identify any time reference:
- Explicit dates: "September 2025", "March 15", "2025-09-01"
- Relative dates: "today", "yesterday", "last week", "past 3 days", "this month"
- Implicit defaults: If no date is mentioned for a data query, the expected behavior is to return recent data (today + past 7 days)

STEP 2: For each bot response that contains dated data (tables with dates, "on Monday", "at 2pm on March 5", etc.), check:

A. DATE RANGE MATCH: Do the dates in the bot's response fall within the time period the user requested?
   - "last week" should produce data from the 7 days preceding the conversation
   - "September" should produce data from September 1-30
   - "yesterday" should produce data from exactly one day ago

B. COMPLETENESS: Did the bot cover the full requested range or only a partial subset?
   - User asks for "this week" but bot only shows Monday and Tuesday → incomplete

C. WRONG PERIOD: Did the bot return data from a completely different time period?
   - User asks about "last week" and bot shows data from 3 weeks ago → wrong period

D. CONSISTENCY: If the bot references dates in its prose, do they match the dates in its tables/data?

STEP 3: If the conversation contains no time-referenced data requests, set has_date_queries to false, score 10, and note in analysis.

SCORING:
- date_accuracy: 1-10 scale
  10 = All date-referenced responses cover the correct time period completely
  7-9 = Correct period but incomplete coverage, or minor off-by-one issues
  4-6 = Partially correct period — some data from the right range, some from wrong
  1-3 = Clearly wrong time period returned, or dates in prose contradict dates in data

Output structure is controlled by the schema - just provide the data.
```

**Output Schema:**

```python
[
    {
        "key": "date_accuracy",
        "type": "number",
        "description": "Accuracy of date/time period handling in bot responses (1-10, or 10 if no date queries)",
        "displayMode": "header",
        "isMainMetric": True,
        "thresholds": {"green": 8, "yellow": 5},
    },
    {
        "key": "has_date_queries",
        "type": "boolean",
        "description": "Whether the conversation contains time-referenced data requests",
        "displayMode": "card",
        "isMainMetric": False,
    },
    {
        "key": "date_mismatches",
        "type": "number",
        "description": "Number of responses where the data period didn't match the user's request",
        "displayMode": "card",
        "isMainMetric": False,
    },
    {
        "key": "analysis",
        "type": "text",
        "description": "Per-response date handling assessment — what was requested vs what was returned",
        "displayMode": "hidden",
        "isMainMetric": False,
        "role": "reasoning",
    },
]
```

**`show_in_header`: False** — not every conversation involves date queries.

---

## Schema Design Rationale

All 4 evaluators follow the established pattern:

1. **One `isMainMetric: True` field** — always first, always `displayMode: "header"`. This is what `_extract_scores()` pulls into `summary.overall_score` for the EvalRun.
2. **2-3 supporting metric fields** — `displayMode: "card"`, provide quick-glance context.
3. **One reasoning/analysis field** — `displayMode: "hidden"`, `role: "reasoning"`. Full LLM explanation, shown on detail view only.
4. **`thresholds`** — `green` and `yellow` values calibrated to each score range. The schema_generator ignores these (they're UI-only metadata), but they drive the color-coding in the eval run cards.
5. **Field types** — only `number`, `boolean`, `text` used. These are the well-tested types in `schema_generator._generate_field_schema()`. No `array` or `enum` needed here.
