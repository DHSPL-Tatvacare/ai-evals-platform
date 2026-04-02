"""Phase 1 prompt contract tests."""

import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.prompt import Prompt
from app.models.mixins.shareable import Visibility
from app.schemas.prompt import PromptCreate, PromptResponse


def test_prompt_create_accepts_branch_key_and_visibility():
    payload = PromptCreate(
        appId="voice-rx",
        promptType="transcription",
        branchKey="branch-123",
        name="Transcript Prompt",
        prompt="Extract transcript",
        visibility="app",
    )

    dumped = payload.model_dump(by_alias=True)

    assert dumped["branchKey"] == "branch-123"
    assert dumped["visibility"] == Visibility.APP


def test_prompt_response_serializes_branch_metadata():
    prompt = Prompt(
        id=1,
        app_id="voice-rx",
        prompt_type="transcription",
        branch_key="branch-123",
        version=2,
        name="Transcript Prompt",
        prompt="Extract transcript",
        description="",
        is_default=False,
        visibility=Visibility.APP,
        forked_from=7,
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    payload = PromptResponse.model_validate(prompt).model_dump(by_alias=True, mode="json")

    assert payload["branchKey"] == "branch-123"
    assert payload["visibility"] == "app"
    assert payload["forkedFrom"] == 7


def test_prompt_model_uses_branch_aware_version_uniqueness():
    constraint_names = {constraint.name for constraint in Prompt.__table__.constraints}

    assert "uq_prompt_branch_version" in constraint_names
    assert "branch_key" in Prompt.__table__.columns
