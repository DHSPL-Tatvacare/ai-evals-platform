# Phase 2 — Aggregation Engine

## Objective

Build the pure-computation layer that transforms raw `ThreadEvaluation` and `AdversarialEvaluation` rows into structured analytics: verdict distributions, rule compliance matrix, friction analysis, exemplar selection, and adversarial breakdown. No LLM calls — just data crunching.

## Pre-flight

- Branch: `feat/report-phase-2-aggregation` from `main` (Phase 1 merged)
- All work in: `backend/app/services/reports/aggregator.py`
- Input: lists of ORM model instances (ThreadEvaluation, AdversarialEvaluation, EvalRun)
- Output: Pydantic schema instances from Phase 1's `schemas.py`

---

## Step 1: Aggregator Class Structure

### `backend/app/services/reports/aggregator.py`

```python
"""
Pure data aggregation — no DB access, no LLM calls.

Receives loaded data, returns structured analytics.
All methods are sync (no async needed for computation).
"""

from app.services.reports.schemas import (
    VerdictDistributions, IntentHistogram, CustomEvalSummary,
    RuleComplianceMatrix, RuleComplianceEntry, CoFailure,
    FrictionAnalysis, FrictionPattern,
    AdversarialBreakdown, AdversarialCategoryResult, AdversarialDifficultyResult,
    Exemplars, ExemplarThread, TranscriptMessage, RuleViolation, FrictionTurn,
)


class ReportAggregator:
    """
    Stateless aggregator. Instantiate with raw data, call methods to get sections.

    Usage:
        agg = ReportAggregator(threads, adversarial, summary)
        distributions = agg.compute_distributions()
        compliance = agg.compute_rule_compliance()
        friction = agg.compute_friction_analysis()
        exemplars = agg.select_exemplars(k=5)
        adversarial = agg.compute_adversarial_breakdown()
    """

    def __init__(
        self,
        threads: list,           # ThreadEvaluation ORM instances
        adversarial: list,       # AdversarialEvaluation ORM instances
        run_summary: dict,       # EvalRun.summary
        run_batch_metadata: dict | None,  # EvalRun.batch_metadata
    ):
        self.threads = threads
        self.adversarial = adversarial
        self.summary = run_summary or {}
        self.batch_metadata = run_batch_metadata or {}

    # --- Public methods (one per report section) ---

    def compute_distributions(self) -> VerdictDistributions: ...
    def compute_rule_compliance(self) -> RuleComplianceMatrix: ...
    def compute_friction_analysis(self) -> FrictionAnalysis: ...
    def select_exemplars(self, k: int = 5) -> Exemplars: ...
    def compute_adversarial_breakdown(self) -> AdversarialBreakdown | None: ...
```

### Design:
- Stateless — all data passed in constructor, no side effects
- Each public method returns exactly one report section
- Private helper methods prefixed with `_`
- No imports from `evaluators/` — uses only the raw result dicts from ThreadEvaluation.result

---

## Step 2: Verdict Distributions

### `compute_distributions(self) -> VerdictDistributions`

**Correctness & Efficiency:**
- Already available in `self.summary["correctness_verdicts"]` and `self.summary["efficiency_verdicts"]`
- Pass through directly (they're already `{verdict_name: count}` dicts)
- Normalize verdict keys: replace spaces with underscores for consistency (e.g., "SOFT FAIL" → keep as-is for display, but ensure consistent keys)

**Intent Histogram:**
- Iterate all `self.threads`, extract `thread.intent_accuracy` (float 0–1)
- Bucket into 5 bins: `[0-20, 20-40, 40-60, 60-80, 80-100]`
- Handle None values (skip threads with null intent_accuracy)
- Return `IntentHistogram(buckets=[...], counts=[...])`

```python
def _build_intent_histogram(self) -> IntentHistogram:
    buckets = ["0-20", "20-40", "40-60", "60-80", "80-100"]
    counts = [0, 0, 0, 0, 0]
    for t in self.threads:
        if t.intent_accuracy is None:
            continue
        pct = t.intent_accuracy * 100
        idx = min(int(pct // 20), 4)  # clamp 100% to last bucket
        counts[idx] += 1
    return IntentHistogram(buckets=buckets, counts=counts)
```

**Custom Evaluations:**
- Already in `self.summary.get("custom_evaluations", {})`
- Transform each entry to `CustomEvalSummary`:
  - If `average` exists → type="numeric"
  - If `distribution` exists → type="text"
- Preserve evaluator names from summary

---

## Step 3: Rule Compliance Matrix

### `compute_rule_compliance(self) -> RuleComplianceMatrix`

This is the most complex aggregation. Thread-level `result` dicts contain per-evaluator `rule_compliance` arrays.

**Data extraction path:**
```
ThreadEvaluation.result -> {
    "correctness_evaluations": [
        { "rule_compliance": [{"rule_id": "...", "followed": true, "evidence": "..."}] }
    ],
    "efficiency_evaluation": {
        "rule_compliance": [{"rule_id": "...", "followed": true, "evidence": "..."}]
    }
}
```

**Algorithm:**

```python
def compute_rule_compliance(self) -> RuleComplianceMatrix:
    # 1. Collect all rule compliance entries across all threads
    rule_stats: dict[str, {"passed": int, "failed": int, "section": str}] = {}
    co_failure_tracker: dict[frozenset, int] = {}  # track pairs that fail together
    total_threads_with_rules = 0

    for thread in self.threads:
        result = thread.result or {}
        thread_failures: set[str] = set()

        # Correctness rules (from each message evaluation)
        for ce in result.get("correctness_evaluations", []):
            for rc in ce.get("rule_compliance", []):
                rule_id = rc["rule_id"]
                section = rc.get("section", "")
                if rule_id not in rule_stats:
                    rule_stats[rule_id] = {"passed": 0, "failed": 0, "section": section}
                if rc["followed"]:
                    rule_stats[rule_id]["passed"] += 1
                else:
                    rule_stats[rule_id]["failed"] += 1
                    thread_failures.add(rule_id)

        # Efficiency rules (single evaluation per thread)
        eff = result.get("efficiency_evaluation") or {}
        for rc in eff.get("rule_compliance", []):
            rule_id = rc["rule_id"]
            section = rc.get("section", "")
            if rule_id not in rule_stats:
                rule_stats[rule_id] = {"passed": 0, "failed": 0, "section": section}
            if rc["followed"]:
                rule_stats[rule_id]["passed"] += 1
            else:
                rule_stats[rule_id]["failed"] += 1
                thread_failures.add(rule_id)

        # Track co-failures (pairs of rules that fail in same thread)
        if len(thread_failures) >= 2:
            total_threads_with_rules += 1
            for pair in _combinations(thread_failures, 2):
                key = frozenset(pair)
                co_failure_tracker[key] = co_failure_tracker.get(key, 0) + 1

    # 2. Build rule entries with severity classification
    rules = []
    for rule_id, stats in rule_stats.items():
        total = stats["passed"] + stats["failed"]
        rate = stats["passed"] / total if total > 0 else 0
        severity = _classify_severity(rate, stats["failed"])
        rules.append(RuleComplianceEntry(
            rule_id=rule_id,
            section=stats["section"],
            passed=stats["passed"],
            failed=stats["failed"],
            rate=round(rate, 3),
            severity=severity,
        ))

    # Sort: worst compliance first
    rules.sort(key=lambda r: r.rate)

    # 3. Build co-failure pairs (only those with >= 2 co-occurrences)
    co_failures = []
    for pair, count in co_failure_tracker.items():
        pair_list = sorted(pair)
        # Rate: how often both fail together relative to either failing
        a_fails = rule_stats[pair_list[0]]["failed"]
        b_fails = rule_stats[pair_list[1]]["failed"]
        min_fails = min(a_fails, b_fails)
        co_rate = count / min_fails if min_fails > 0 else 0
        if count >= 2 and co_rate >= 0.3:  # Only report meaningful correlations
            co_failures.append(CoFailure(
                rule_a=pair_list[0],
                rule_b=pair_list[1],
                co_occurrence_rate=round(co_rate, 2),
            ))

    co_failures.sort(key=lambda c: c.co_occurrence_rate, reverse=True)

    return RuleComplianceMatrix(rules=rules, co_failures=co_failures[:5])
```

**Severity classification:**
```python
def _classify_severity(rate: float, fail_count: int) -> str:
    if fail_count == 0:
        return "—"  # no failures
    if rate < 0.5:
        return "CRITICAL"
    if rate < 0.7:
        return "HIGH"
    if rate < 0.85:
        return "MEDIUM"
    return "LOW"
```

### Important notes:
- Correctness has rule_compliance per MESSAGE (multiple per thread) — count each occurrence
- Efficiency has rule_compliance per THREAD (one set) — count once per thread
- The `section` field comes from rule_catalog.py and groups rules visually
- Co-failures use `itertools.combinations` or equivalent
- Only report top 5 co-failure pairs to keep the report focused

---

## Step 4: Friction Analysis

### `compute_friction_analysis(self) -> FrictionAnalysis`

**Data extraction path:**
```
ThreadEvaluation.result -> {
    "efficiency_evaluation": {
        "verdict": "FRICTION",
        "friction_turns": [{"turn": 2, "cause": "bot", "description": "..."}],
        "recovery_quality": "GOOD" | "PARTIAL" | "FAILED" | "NOT_NEEDED"
    }
}
```

**Algorithm:**

```python
def compute_friction_analysis(self) -> FrictionAnalysis:
    bot_turns = 0
    user_turns = 0
    recovery_dist = {"GOOD": 0, "PARTIAL": 0, "FAILED": 0, "NOT_NEEDED": 0}
    verdict_turn_sums: dict[str, list[int]] = {}  # verdict → [turn_counts]
    pattern_tracker: dict[str, {"count": int, "threads": list[str]}] = {}

    for thread in self.threads:
        result = thread.result or {}
        eff = result.get("efficiency_evaluation") or {}

        # Count friction turns by cause
        friction_turns = eff.get("friction_turns", [])
        for ft in friction_turns:
            if ft.get("cause") == "bot":
                bot_turns += 1
            else:
                user_turns += 1

            # Track friction patterns (group by description similarity)
            desc = ft.get("description", "").strip()
            if desc:
                pattern_key = _normalize_pattern(desc)
                if pattern_key not in pattern_tracker:
                    pattern_tracker[pattern_key] = {"count": 0, "threads": [], "description": desc}
                pattern_tracker[pattern_key]["count"] += 1
                if thread.thread_id not in pattern_tracker[pattern_key]["threads"]:
                    pattern_tracker[pattern_key]["threads"].append(thread.thread_id)

        # Recovery quality
        rq = eff.get("recovery_quality", "NOT_NEEDED")
        if rq in recovery_dist:
            recovery_dist[rq] += 1

        # Avg turns by verdict
        verdict = thread.efficiency_verdict or "UNKNOWN"
        msg_count = len(result.get("thread", {}).get("messages", []))
        turn_count = (msg_count + 1) // 2  # pairs of user+assistant = 1 turn
        if verdict not in verdict_turn_sums:
            verdict_turn_sums[verdict] = []
        verdict_turn_sums[verdict].append(turn_count)

    # Compute averages
    avg_turns = {
        v: round(sum(turns) / len(turns), 1)
        for v, turns in verdict_turn_sums.items()
        if turns
    }

    # Top friction patterns (sorted by count DESC)
    top_patterns = sorted(
        pattern_tracker.values(),
        key=lambda p: p["count"],
        reverse=True,
    )[:5]

    return FrictionAnalysis(
        total_friction_turns=bot_turns + user_turns,
        by_cause={"bot": bot_turns, "user": user_turns},
        recovery_quality=recovery_dist,
        avg_turns_by_verdict=avg_turns,
        top_patterns=[
            FrictionPattern(
                description=p["description"],
                count=p["count"],
                example_thread_ids=p["threads"][:3],
            )
            for p in top_patterns
        ],
    )
```

**Pattern normalization:**

Friction turn descriptions are free-text from the LLM. Exact dedup won't work. Use simple normalization:

```python
def _normalize_pattern(desc: str) -> str:
    """Rough grouping key — lowercase, strip punctuation, first 6 words."""
    import re
    cleaned = re.sub(r'[^\w\s]', '', desc.lower())
    words = cleaned.split()[:6]
    return ' '.join(words)
```

This isn't perfect but groups similar patterns (e.g., "Bot re-asked for time" and "Bot re-asked for the time" map to same key). The AI narrator in Phase 3 will provide a cleaner narrative on top of this.

---

## Step 5: Exemplar Selection

### `select_exemplars(self, k: int = 5) -> Exemplars`

**Composite scoring:**
```python
CORRECTNESS_ORDINAL = {
    "PASS": 1.0,
    "NOT APPLICABLE": 0.8,
    "NOT_APPLICABLE": 0.8,
    "SOFT FAIL": 0.5,
    "SOFT_FAIL": 0.5,
    "HARD FAIL": 0.2,
    "HARD_FAIL": 0.2,
    "CRITICAL": 0.0,
}

EFFICIENCY_ORDINAL = {
    "EFFICIENT": 1.0,
    "ACCEPTABLE": 0.7,
    "INCOMPLETE": 0.4,
    "FRICTION": 0.2,
    "BROKEN": 0.0,
}

def _compute_composite_score(self, thread) -> float:
    intent = thread.intent_accuracy if thread.intent_accuracy is not None else 0.5
    correctness = CORRECTNESS_ORDINAL.get(thread.worst_correctness or "", 0.5)
    efficiency = EFFICIENCY_ORDINAL.get(thread.efficiency_verdict or "", 0.5)
    task = 1.0 if thread.success_status else 0.0
    return (intent * 0.25) + (correctness * 0.25) + (efficiency * 0.25) + (task * 0.25)
```

**Selection:**
```python
def select_exemplars(self, k: int = 5) -> Exemplars:
    scored = [
        (self._compute_composite_score(t), t)
        for t in self.threads
    ]
    scored.sort(key=lambda x: x[0], reverse=True)

    best = [self._build_exemplar(score, t) for score, t in scored[:k]]
    worst = [self._build_exemplar(score, t) for score, t in scored[-k:]]
    worst.reverse()  # worst first

    return Exemplars(best=best, worst=worst)
```

**Building exemplar detail:**
```python
def _build_exemplar(self, score: float, thread) -> ExemplarThread:
    result = thread.result or {}

    # Extract transcript
    thread_data = result.get("thread", {})
    messages = thread_data.get("messages", [])
    transcript = [
        TranscriptMessage(
            role=m.get("role", "user"),
            content=m.get("content", ""),
        )
        for m in messages
    ]

    # Extract rule violations (failed rules across all evaluators)
    violations = []
    for ce in result.get("correctness_evaluations", []):
        for rc in ce.get("rule_compliance", []):
            if not rc.get("followed", True):
                violations.append(RuleViolation(
                    rule_id=rc["rule_id"],
                    evidence=rc.get("evidence", ""),
                ))
    eff = result.get("efficiency_evaluation") or {}
    for rc in eff.get("rule_compliance", []):
        if not rc.get("followed", True):
            violations.append(RuleViolation(
                rule_id=rc["rule_id"],
                evidence=rc.get("evidence", ""),
            ))

    # Deduplicate violations by rule_id (keep first)
    seen_rules = set()
    unique_violations = []
    for v in violations:
        if v.rule_id not in seen_rules:
            seen_rules.add(v.rule_id)
            unique_violations.append(v)

    # Extract friction turns
    friction_turns = [
        FrictionTurn(
            turn=ft.get("turn", 0),
            cause=ft.get("cause", "bot"),
            description=ft.get("description", ""),
        )
        for ft in eff.get("friction_turns", [])
    ]

    return ExemplarThread(
        thread_id=thread.thread_id,
        composite_score=round(score, 3),
        intent_accuracy=thread.intent_accuracy,
        correctness_verdict=thread.worst_correctness,
        efficiency_verdict=thread.efficiency_verdict,
        task_completed=bool(thread.success_status),
        transcript=transcript,
        rule_violations=unique_violations,
        friction_turns=friction_turns,
    )
```

### Important:
- Transcript is included in full — the PDF and UI will show it
- Transcript messages should be truncated if excessively long (>500 chars) — add a `[:500]` clamp on content to keep payload size manageable
- Violations are deduped by rule_id per thread (same rule can fire on multiple messages)

---

## Step 6: Adversarial Breakdown

### `compute_adversarial_breakdown(self) -> AdversarialBreakdown | None`

```python
def compute_adversarial_breakdown(self) -> AdversarialBreakdown | None:
    if not self.adversarial:
        return None

    # By category
    category_stats: dict[str, {"passed": int, "total": int}] = {}
    difficulty_stats: dict[str, {"passed": int, "total": int}] = {}

    for ae in self.adversarial:
        cat = ae.category or "unknown"
        diff = ae.difficulty or "UNKNOWN"
        is_pass = ae.verdict in ("PASS",)

        if cat not in category_stats:
            category_stats[cat] = {"passed": 0, "total": 0}
        category_stats[cat]["total"] += 1
        if is_pass:
            category_stats[cat]["passed"] += 1

        if diff not in difficulty_stats:
            difficulty_stats[diff] = {"passed": 0, "total": 0}
        difficulty_stats[diff]["total"] += 1
        if is_pass:
            difficulty_stats[diff]["passed"] += 1

    by_category = sorted(
        [
            AdversarialCategoryResult(
                category=cat,
                passed=s["passed"],
                total=s["total"],
                pass_rate=round(s["passed"] / s["total"], 3) if s["total"] > 0 else 0,
            )
            for cat, s in category_stats.items()
        ],
        key=lambda x: x.pass_rate,  # worst first
    )

    by_difficulty = [
        AdversarialDifficultyResult(
            difficulty=diff,
            passed=s["passed"],
            total=s["total"],
        )
        for diff, s in sorted(difficulty_stats.items(), key=lambda x: ["EASY", "MEDIUM", "HARD"].index(x[0]) if x[0] in ["EASY", "MEDIUM", "HARD"] else 99)
    ]

    return AdversarialBreakdown(by_category=by_category, by_difficulty=by_difficulty)
```

---

## Step 7: Wire Aggregator into ReportService

Update `report_service.py` to use the aggregator:

```python
# In ReportService.generate():

from .aggregator import ReportAggregator

async def generate(self, run_id: str) -> ReportPayload:
    run = await self._load_run(run_id)
    threads = await self._load_threads(run_id)
    adversarial = await self._load_adversarial(run_id)

    # Compute health score
    summary = run.summary or {}
    health_score = compute_health_score(
        avg_intent_accuracy=summary.get("avg_intent_accuracy"),
        correctness_verdicts=summary.get("correctness_verdicts", {}),
        efficiency_verdicts=summary.get("efficiency_verdicts", {}),
        total_evaluated=summary.get("completed", 0),
        success_count=self._count_successes(threads),
    )

    # Aggregate
    agg = ReportAggregator(threads, adversarial, summary, run.batch_metadata)
    distributions = agg.compute_distributions()
    rule_compliance = agg.compute_rule_compliance()
    friction = agg.compute_friction_analysis()
    exemplars = agg.select_exemplars(k=5)
    adversarial_breakdown = agg.compute_adversarial_breakdown()

    # Metadata
    metadata = self._build_metadata(run, threads, adversarial)

    return ReportPayload(
        metadata=metadata,
        health_score=health_score,
        distributions=distributions,
        rule_compliance=rule_compliance,
        friction=friction,
        adversarial=adversarial_breakdown,
        exemplars=exemplars,
        production_prompts=ProductionPrompts(
            intent_classification=None,
            meal_summary_spec=None,
        ),
        narrative=None,  # Phase 3
    )

def _count_successes(self, threads) -> int:
    return sum(1 for t in threads if t.success_status)
```

---

## Verification Checklist

- [ ] `GET /api/reports/{run_id}` returns fully populated distributions, rule_compliance, friction, exemplars
- [ ] Health score grade matches manual calculation
- [ ] Rule compliance matrix shows all 13 rules with correct pass/fail counts
- [ ] Co-failure pairs are reasonable (rate > 0.3, count >= 2)
- [ ] Exemplars: best 5 have highest composite scores, worst 5 have lowest
- [ ] Exemplar transcripts are present and not empty
- [ ] Adversarial breakdown is null when run has no adversarial data
- [ ] Adversarial breakdown shows correct per-category pass rates
- [ ] Friction patterns are grouped sensibly (not 1 pattern per thread)
- [ ] Intent histogram buckets sum to total threads with intent data
- [ ] Custom evaluation summaries match what's in run.summary

## Performance Notes

- All computation is in-memory after initial DB load
- Typical run: 20-50 threads → < 100ms aggregation
- Large run: 1000 threads → still < 1s (no LLM calls, just dict traversal)
- If runs exceed 5000 threads, consider streaming thread loading — but not needed now
