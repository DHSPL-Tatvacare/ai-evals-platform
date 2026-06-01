"""Pure-mapper tests for map_template_variables (Task #7).

Drives the pure function only — no DB, no pack. Verifies exact + fuzzy
binding, that an unmappable placeholder lands in `unmatched` (never bound to
a guess), and that `payload_fields_to_add` equals exactly the matched set
(the back-propagation rule onto source.cohort.payload_fields).
"""
import unittest

from app.services.orchestration_authoring.variable_mapper import map_variables


class MapVariablesExactTests(unittest.TestCase):
    def test_exact_match_binds_payload_field(self) -> None:
        result = map_variables(
            placeholders=["first_name", "city"],
            fields=["first_name", "city", "lead_score"],
        )
        rows = {m["agent_variable"]: m for m in result["mappings"]}
        self.assertEqual(set(rows), {"first_name", "city"})
        self.assertEqual(rows["first_name"]["source_kind"], "payload")
        self.assertEqual(rows["first_name"]["payload_field"], "first_name")
        self.assertEqual(rows["city"]["payload_field"], "city")
        self.assertEqual(result["unmatched"], [])

    def test_normalized_match_binds(self) -> None:
        # "First Name" placeholder normalizes to the "first_name" field.
        result = map_variables(
            placeholders=["First Name"],
            fields=["first_name"],
        )
        self.assertEqual(len(result["mappings"]), 1)
        self.assertEqual(result["mappings"][0]["agent_variable"], "First Name")
        self.assertEqual(result["mappings"][0]["payload_field"], "first_name")
        self.assertEqual(result["unmatched"], [])


class MapVariablesFuzzyTests(unittest.TestCase):
    def test_fuzzy_close_match_binds(self) -> None:
        # "phone_numbr" is a difflib-close match to "phone_number".
        result = map_variables(
            placeholders=["phone_numbr"],
            fields=["phone_number", "email"],
        )
        self.assertEqual(len(result["mappings"]), 1)
        self.assertEqual(result["mappings"][0]["payload_field"], "phone_number")
        self.assertEqual(result["unmatched"], [])


class MapVariablesUnmatchedTests(unittest.TestCase):
    def test_unmappable_placeholder_is_not_bound_to_a_guess(self) -> None:
        result = map_variables(
            placeholders=["appointment_slot"],
            fields=["first_name", "city"],
        )
        self.assertEqual(result["mappings"], [])
        self.assertEqual(result["unmatched"], ["appointment_slot"])
        self.assertEqual(result["payload_fields_to_add"], [])


class MapVariablesBackPropTests(unittest.TestCase):
    def test_payload_fields_to_add_equals_matched_field_set(self) -> None:
        result = map_variables(
            placeholders=["first_name", "city", "unknown_thing"],
            fields=["first_name", "city", "lead_score"],
        )
        self.assertEqual(set(result["payload_fields_to_add"]), {"first_name", "city"})
        self.assertEqual(result["unmatched"], ["unknown_thing"])

    def test_payload_fields_to_add_has_no_duplicates(self) -> None:
        # Two placeholders matching the same field contribute one field.
        result = map_variables(
            placeholders=["first_name", "First Name"],
            fields=["first_name"],
        )
        self.assertEqual(result["payload_fields_to_add"], ["first_name"])


if __name__ == "__main__":
    unittest.main()
