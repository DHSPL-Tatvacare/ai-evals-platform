"""Phase 1 app config contract tests."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.app import App
from app.schemas.app_config import AppConfig


def test_app_model_includes_config_column():
    assert "config" in App.__table__.columns


def test_app_config_schema_matches_phase_one_shape():
    payload = AppConfig(
        displayName="Kaira Bot",
        icon="kaira-bot",
        description="Health chat bot assistant",
        features={
            "hasRules": True,
            "hasAdversarial": True,
        },
        rules={
            "catalogSource": "settings",
            "catalogKey": "rule-catalog",
            "autoMatch": True,
        },
        evaluator={
            "defaultVisibility": "private",
            "defaultModel": "gemini-2.5-flash",
            "variables": [
                {
                    "key": "chat_transcript",
                    "displayName": "Chat Transcript",
                    "description": "Full conversation history",
                    "category": "Conversation",
                }
            ],
            "dynamicVariableSources": {
                "registry": True,
                "listingApiPaths": False,
            },
        },
        assetDefaults={
            "evaluator": "private",
            "prompt": "private",
            "schema": "private",
            "adversarialContract": "app",
            "llmSettings": "private",
        },
        evalRun={"supportedTypes": ["custom", "batch_thread"]},
    )

    dumped = payload.model_dump(by_alias=True)

    assert dumped["displayName"] == "Kaira Bot"
    assert dumped["features"]["hasRules"] is True
    assert dumped["rules"]["catalogKey"] == "rule-catalog"
    assert dumped["evaluator"]["dynamicVariableSources"]["registry"] is True
    assert dumped["assetDefaults"]["adversarialContract"] == "app"
    assert dumped["evalRun"]["supportedTypes"] == ["custom", "batch_thread"]
