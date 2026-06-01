"""Cat-A picker resolution for wati_template_picker.

`match_template` is pure: it matches a free-text intent against the WATI
template list (the SAME items list_connection_wati_templates returns) via
stdlib difflib. It NEVER passes through an unmatched intent as a template
name — an unknown intent resolves to `not_found` so the handler asks.

Fixture items are verbatim normalised WATI template shapes
({name, language, status, parameters, body, body_original}) as produced by
WatiAdapter.list_message_templates / _normalize_template_candidate.
"""
from __future__ import annotations

import unittest

from app.services.orchestration_authoring.template_resolver import (
    TemplateMatch,
    match_template,
)


# Verbatim normalised WATI getMessageTemplates items (post _normalize_template_candidate).
_TEMPLATES: list[dict] = [
    {
        "name": "document_approved_latest",
        "language": "en",
        "status": "APPROVED",
        "parameters": ["name", "documentType"],
        "body": "Hi *{{1}}*,\nyour *{{2}}* has been approved.",
        "body_original": "Hi *{{name}}*,\nyour *{{documentType}}* has been approved.",
    },
    {
        "name": "appointment_reminder",
        "language": "en",
        "status": "APPROVED",
        "parameters": ["name", "date"],
        "body": "Hi {{1}}, your appointment is on {{2}}.",
        "body_original": None,
    },
    {
        "name": "appointment_confirmation",
        "language": "en",
        "status": "APPROVED",
        "parameters": ["name"],
        "body": "Hi {{1}}, your appointment is confirmed.",
        "body_original": None,
    },
]


class MatchTemplateTests(unittest.TestCase):
    def test_exact_name_resolves_with_placeholders(self) -> None:
        result = match_template(templates=_TEMPLATES, intent="document_approved_latest")
        self.assertIsInstance(result, TemplateMatch)
        self.assertEqual(result.status, "resolved")
        self.assertEqual(result.name, "document_approved_latest")
        self.assertEqual(result.placeholders, ["name", "documentType"])

    def test_exact_name_is_case_insensitive(self) -> None:
        result = match_template(templates=_TEMPLATES, intent="Document_Approved_Latest")
        self.assertEqual(result.status, "resolved")
        self.assertEqual(result.name, "document_approved_latest")

    def test_fuzzy_near_name_resolves(self) -> None:
        # A near-miss on a single distinctive name resolves to that template.
        result = match_template(templates=_TEMPLATES, intent="document approved")
        self.assertEqual(result.status, "resolved")
        self.assertEqual(result.name, "document_approved_latest")
        self.assertEqual(result.placeholders, ["name", "documentType"])

    def test_ambiguous_intent_returns_pick_list(self) -> None:
        # "appointment" is close to BOTH appointment_* templates → pick.
        result = match_template(templates=_TEMPLATES, intent="appointment")
        self.assertEqual(result.status, "pick")
        self.assertIn("appointment_reminder", result.candidates)
        self.assertIn("appointment_confirmation", result.candidates)
        # A pick MUST NOT pre-pick a name.
        self.assertIsNone(result.name)

    def test_unknown_intent_returns_not_found_never_passthrough(self) -> None:
        result = match_template(templates=_TEMPLATES, intent="zzz_totally_unrelated")
        self.assertEqual(result.status, "not_found")
        # NEVER surface the raw intent as a resolved template name.
        self.assertIsNone(result.name)
        self.assertEqual(result.placeholders, [])

    def test_empty_template_list_is_not_found(self) -> None:
        result = match_template(templates=[], intent="anything")
        self.assertEqual(result.status, "not_found")
        self.assertIsNone(result.name)


if __name__ == "__main__":
    unittest.main()
