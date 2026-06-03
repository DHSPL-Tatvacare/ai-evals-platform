"""Unit tests for reports' spine-source reconstruction (run-level rollups rebuilt from the spine)."""
import unittest

from app.services.reports.spine_source import (
    AdversarialEvidence,
    ThreadEvidence,
    _build_transcript_summary,
    reconstruct_adversarial_summary,
    reconstruct_thread_summary,
)


def _thread(tid, intent=None, worst=None, eff=None, success=False, result=None):
    return ThreadEvidence(
        thread_id=tid, result=result or {}, intent_accuracy=intent,
        worst_correctness=worst, efficiency_verdict=eff, success_status=success,
    )


class ReconstructThreadSummary(unittest.TestCase):
    def test_tallies_verdicts_and_intent_mean(self):
        threads = [
            _thread("a", intent=1.0, worst="PASS", eff="ACCEPTABLE", success=True),
            _thread("b", intent=0.5, worst="PASS", eff="INCOMPLETE"),
            _thread("c", intent=0.0, worst="CRITICAL", eff="INCOMPLETE"),
        ]
        s = reconstruct_thread_summary(threads)
        self.assertEqual(s["correctness_verdicts"], {"PASS": 2, "CRITICAL": 1})
        self.assertEqual(s["efficiency_verdicts"], {"ACCEPTABLE": 1, "INCOMPLETE": 2})
        self.assertEqual(s["avg_intent_accuracy"], 0.5)
        self.assertEqual(s["total_threads"], 3)
        self.assertEqual(s["completed"], 3)
        self.assertEqual(s["errors"], 0)

    def test_insertion_order_preserved_in_distribution_keys(self):
        # First-occurrence order across the (pre-ordered) thread list drives the dict order.
        threads = [_thread("a", eff="INCOMPLETE"), _thread("b", eff="ACCEPTABLE")]
        s = reconstruct_thread_summary(threads)
        self.assertEqual(list(s["efficiency_verdicts"].keys()), ["INCOMPLETE", "ACCEPTABLE"])

    def test_omits_absent_dimensions(self):
        s = reconstruct_thread_summary([_thread("a")])
        self.assertNotIn("correctness_verdicts", s)
        self.assertNotIn("efficiency_verdicts", s)
        self.assertNotIn("avg_intent_accuracy", s)

    def test_custom_evaluations_union(self):
        threads = [
            _thread("a", result={"custom_evaluations": {"ev1": {}}}),
            _thread("b", result={"custom_evaluations": {"ev1": {}, "ev2": {}}}),
        ]
        s = reconstruct_thread_summary(threads)
        self.assertEqual(set(s["custom_evaluations"].keys()), {"ev1", "ev2"})


class ReconstructAdversarialSummary(unittest.TestCase):
    def test_total_and_zero_errors_for_normal_cases(self):
        adv = [
            AdversarialEvidence(id="1", result={"verdict": "PASS"}, verdict="PASS", goal_achieved=True),
            AdversarialEvidence(id="2", result={"verdict": "HARD FAIL"}, verdict="HARD FAIL"),
        ]
        s = reconstruct_adversarial_summary(adv)
        self.assertEqual(s["total_tests"], 2)
        self.assertEqual(s["errors"], 0)


class BuildTranscriptSummary(unittest.TestCase):
    def test_upload_flow_segment_stats(self):
        result = {
            "status": "completed",
            "flowType": "upload",
            "judgeOutput": {"segments": []},
            "critique": {
                "statistics": {"totalSegments": 4, "matchCount": 3},
                "segments": [
                    {"severity": "MINOR"}, {"severity": "MINOR"},
                    {"severity": "CRITICAL"},
                ],
            },
        }
        s = _build_transcript_summary(result)
        self.assertEqual(s["flow_type"], "upload")
        self.assertEqual(s["completeness"], "full")
        self.assertEqual(s["total_items"], 4)
        self.assertEqual(s["overall_accuracy"], 0.75)
        self.assertEqual(s["severity_distribution"], {"MINOR": 2, "CRITICAL": 1})


if __name__ == "__main__":
    unittest.main()
