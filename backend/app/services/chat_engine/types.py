"""Shared types for the provider-native chat engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Provider-agnostic representation of a single tool/function call."""
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ChatAdapter(Protocol):
    """
    Protocol that each provider adapter implements.
    Messages are opaque — the runner never inspects them.
    """

    async def send(
        self,
        messages: list[Any],
        tools: list[dict[str, Any]],
        system: str,
        temperature: float,
    ) -> Any:
        """Send conversation to the LLM. Returns provider-native response."""
        ...

    def build_user_message(self, text: str) -> Any:
        """Create a user message in provider-native format."""
        ...

    def build_tool_result(self, tool_call: ToolCall, result: str) -> Any:
        """Create a tool result message in provider-native format."""
        ...

    def extract_response_message(self, response: Any) -> Any:
        """Extract the storable message from a provider response. Opaque to runner."""
        ...

    def extract_tool_calls(self, response: Any) -> list[ToolCall]:
        """Extract tool calls from response. Empty list = no tool calls."""
        ...

    def extract_text(self, response: Any) -> str:
        """Extract final text content from response."""
        ...

    def serialize(self, messages: list[Any]) -> list[dict]:
        """Serialize provider-native messages to JSON-safe dicts for storage."""
        ...

    def deserialize(self, data: list[dict]) -> list[Any]:
        """Reconstruct provider-native messages from stored dicts."""
        ...
