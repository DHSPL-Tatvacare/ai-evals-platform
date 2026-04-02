"""App config contract tests — Phase 1 shape + Phase 2 seed configs."""

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


def test_app_config_validates_all_required_keys():
    """App config schema enforces all top-level keys for each app config."""
    required_keys = {"displayName", "icon", "description", "features", "rules", "evaluator", "assetDefaults", "evalRun"}

    # Validate that a minimal valid config contains all required keys
    config = AppConfig(
        displayName="Test",
        icon="test",
        description="test",
        features={},
        rules={},
        evaluator={
            "defaultVisibility": "private",
            "defaultModel": "",
            "variables": [],
            "dynamicVariableSources": {},
        },
        assetDefaults={},
        evalRun={"supportedTypes": []},
    )
    dumped = config.model_dump(by_alias=True)
    assert required_keys.issubset(dumped.keys())


def test_kaira_bot_style_config_enables_rules_and_adversarial():
    """Kaira Bot config shape: rules + adversarial enabled, rubric disabled."""
    from app.schemas.app_config import AppFeaturesConfig
    features = AppFeaturesConfig(hasRules=True, hasAdversarial=True, hasRubricMode=False)
    assert features.has_rules is True
    assert features.has_adversarial is True
    assert features.has_rubric_mode is False


def test_voice_rx_style_config_enables_transcription():
    """Voice Rx config shape: transcription enabled, rules disabled."""
    from app.schemas.app_config import AppFeaturesConfig
    features = AppFeaturesConfig(hasTranscription=True, hasRules=False)
    assert features.has_transcription is True
    assert features.has_rules is False


def test_inside_sales_style_config_enables_rubric_and_csv():
    """Inside Sales config shape: rubric mode + CSV import enabled."""
    from app.schemas.app_config import AppFeaturesConfig
    features = AppFeaturesConfig(hasRubricMode=True, hasCsvImport=True)
    assert features.has_rubric_mode is True
    assert features.has_csv_import is True
