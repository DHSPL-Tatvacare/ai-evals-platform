"""Rule catalog schema contract tests."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.schemas.rule_catalog import RuleCatalogEntry, RuleCatalogResponse


def test_rule_catalog_response_serializes_camel_case_entries():
    payload = RuleCatalogResponse(
        rules=[
            RuleCatalogEntry(
                ruleId="ask_clarifying_question",
                section="Conversation",
                ruleText="Ask a clarifying question before acting",
                tags=["clarification"],
            )
        ]
    ).model_dump(by_alias=True)

    assert payload["rules"][0]["ruleId"] == "ask_clarifying_question"
    assert payload["rules"][0]["ruleText"] == "Ask a clarifying question before acting"
