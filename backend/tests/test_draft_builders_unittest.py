"""Unit tests for runner output → EvaluationDraft mappers (pure, no DB)."""
import unittest
from types import SimpleNamespace

from app.services.evaluators.draft_builders import (
    adversarial_drafts,
    custom_drafts,
    thread_drafts,
    transcript_drafts,
)


def _rc(rule_id, section, status):
    return SimpleNamespace(rule_id=rule_id, section=section, status=status, followed=None, evidence=f"ev-{rule_id}")


class ThreadDraftsTest(unittest.TestCase):
    def test_correctness_and_efficiency_emit_rule_atoms(self):
        correctness = [SimpleNamespace(
            verdict="HARD FAIL",
            rule_compliance=[_rc("R1", "greeting", "FOLLOWED"), _rc("R2", "safety", "VIOLATED")],
        )]
        efficiency = SimpleNamespace(verdict="FRICTION", rule_compliance=[_rc("R3", "flow", "NOT_APPLICABLE")])
        drafts = thread_drafts(thread_id="t1", correctness_results=correctness, efficiency_result=efficiency)
        by_eval = {d.evaluator.name: d for d in drafts}
        self.assertEqual(by_eval["correctness"].headline.verdict, "HARD FAIL")
        statuses = {a.key: a.status for a in by_eval["correctness"].details}
        self.assertEqual(statuses, {"R1": "PASS", "R2": "FAIL"})
        self.assertTrue(all(a.style == "rule" for a in by_eval["correctness"].details))
        self.assertEqual(by_eval["efficiency"].details[0].status, "NA")

    def test_intent_emits_dimension_accuracy(self):
        intents = [SimpleNamespace(is_correct_intent=True), SimpleNamespace(is_correct_intent=False)]
        drafts = thread_drafts(thread_id="t1", intent_results=intents)
        d = drafts[0]
        self.assertEqual(d.evaluator.name, "intent")
        self.assertEqual(d.details[0].style, "dimension")
        self.assertEqual(d.details[0].score, 0.5)
        self.assertTrue(d.details[0].is_main)


class CustomDraftsTest(unittest.TestCase):
    def test_numeric_fields_become_dimensions_with_main_flag(self):
        schema = [
            {"key": "rapport", "label": "Rapport", "type": "number", "thresholds": {"green": 10}},
            {"key": "overall", "label": "Overall", "type": "number", "thresholds": {"green": 10}},
            {"key": "notes", "type": "text"},
        ]
        output = {"rapport": 8, "overall": 7, "notes": "ok"}
        scores = {"overall_score": 7, "max_score": 10, "reasoning": "fine",
                  "metadata": {"main_metric_key": "overall"}}
        drafts = custom_drafts(target_key="listing-1", target_type="transcript", output=output,
                               output_schema=schema, scores=scores, evaluator_name="rubric")
        d = drafts[0]
        keys = {a.key for a in d.details}
        self.assertEqual(keys, {"rapport", "overall"})  # text field excluded
        self.assertTrue(all(a.style == "dimension" for a in d.details))
        main = [a for a in d.details if a.is_main]
        self.assertEqual(len(main), 1)
        self.assertEqual(main[0].key, "overall")
        self.assertEqual(d.headline.score, 7)


class TranscriptDraftsTest(unittest.TestCase):
    def test_segments_become_comparison_atoms(self):
        evaluation = {"critique": {"segments": [
            {"category": "dosage", "segmentIndex": 4, "severity": "CRITICAL",
             "originalText": "5mg", "judgeText": "50mg", "discrepancy": "10x"},
        ]}}
        drafts = transcript_drafts(target_key="call-1", evaluation=evaluation,
                                   summary={"overall_accuracy": 0.9})
        d = drafts[0]
        a = d.details[0]
        self.assertEqual(a.style, "comparison")
        self.assertEqual(a.locator, "segment:4")
        self.assertEqual(a.severity, "critical")
        self.assertEqual(a.reference_text, "5mg")
        self.assertEqual(a.candidate_text, "50mg")
        self.assertEqual(d.headline.key, "overall_accuracy")

    def test_field_critiques_become_comparison_atoms(self):
        evaluation = {"critique": {"fieldCritiques": [
            {"fieldName": "bp", "apiValue": "120/80", "expectedValue": "130/85", "severity": "MINOR"},
        ]}}
        d = transcript_drafts(target_key="call-2", evaluation=evaluation)[0]
        a = d.details[0]
        self.assertEqual(a.style, "comparison")
        self.assertEqual(a.locator, "api_field:bp")
        self.assertEqual(a.candidate_text, "120/80")
        self.assertEqual(a.reference_text, "130/85")
        self.assertEqual(a.severity, "minor")


class AdversarialDraftsTest(unittest.TestCase):
    def test_rule_compliance_becomes_rule_atoms_with_goal_headline(self):
        evaluation = SimpleNamespace(
            verdict="FAIL", goal_achieved=False,
            rule_compliance=[_rc("A1", "persona", "VIOLATED")],
        )
        d = adversarial_drafts(case_label="case-1", evaluation=evaluation, difficulty="hard",
                               goal_flow=["meal_logged"], active_traits=["ambiguous_qty"])[0]
        self.assertEqual(d.target.type, "test_case")
        self.assertEqual(d.target.attributes["difficulty"], "hard")
        self.assertEqual(d.headline.verdict, "FAIL")
        self.assertEqual(d.headline.score, 0.0)
        self.assertEqual(d.details[0].style, "rule")
        self.assertEqual(d.details[0].status, "FAIL")


if __name__ == "__main__":
    unittest.main()
