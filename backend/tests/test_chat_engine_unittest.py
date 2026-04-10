"""Unit tests for the chat_engine package."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.chat_engine.types import ToolCall


def test_tool_call_fields():
    tc = ToolCall(id="call_1", name="list_section_types", arguments={"foo": "bar"})
    assert tc.id == "call_1"
    assert tc.name == "list_section_types"
    assert tc.arguments == {"foo": "bar"}


def test_tool_call_empty_arguments():
    tc = ToolCall(id="call_2", name="get_detail", arguments={})
    assert tc.arguments == {}
