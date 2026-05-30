import unittest

from app.services.sherlock_v3 import compaction


class CompactionThresholdTests(unittest.TestCase):
    def test_threshold_is_ratio_of_window(self):
        self.assertEqual(
            compaction.CONTEXT_COMPACT_THRESHOLD_TOKENS,
            round(
                compaction.CONTEXT_COMPACT_RATIO
                * compaction.MODEL_CONTEXT_WINDOW_TOKENS
            ),
        )

    def test_threshold_not_temp_debug_value(self):
        self.assertNotEqual(compaction.CONTEXT_COMPACT_THRESHOLD_TOKENS, 20_000)
        self.assertGreaterEqual(compaction.CONTEXT_COMPACT_THRESHOLD_TOKENS, 90_000)

    def test_window_and_ratio_resolved_values(self):
        self.assertEqual(compaction.MODEL_CONTEXT_WINDOW_TOKENS, 1_050_000)
        self.assertEqual(compaction.CONTEXT_COMPACT_RATIO, 0.9)
        self.assertEqual(compaction.CONTEXT_COMPACT_THRESHOLD_TOKENS, 945_000)


if __name__ == '__main__':
    unittest.main()
