"""Test doubles for the agent factory (NOT production code).

``ScriptedToolCallingModel`` is a deterministic ``BaseChatModel`` that returns a
queued sequence of AI messages, ignoring the bound tools. It lets us drive the
**real** ``create_deep_agent`` ReAct loop (real tool execution, real ToolStrategy
structured output) entirely offline — no provider, no API key — which is exactly
what the Step-4 acceptance check needs. This is a legitimate test fixture, not a
re-implementation of a framework primitive (R2 concerns production code).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.agents.factory import ModelProvider
from app.models_layer.resolver import AgentModelRef


class ScriptedToolCallingModel(BaseChatModel):
    """Returns pre-scripted AI messages in order; ``bind_tools`` is a no-op."""

    responses: list[BaseMessage] = []
    cursor: int = 0

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> ScriptedToolCallingModel:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        message = self.responses[self.cursor]
        self.cursor += 1
        return ChatResult(generations=[ChatGeneration(message=message)])

    @property
    def _llm_type(self) -> str:
        return "scripted-tool-calling"


class RecordingModelProvider(ModelProvider):
    """A :class:`ModelProvider` that returns a fixed model and records the gate."""

    def __init__(self, model: BaseChatModel) -> None:
        self._model = model
        self.calls: list[tuple[AgentModelRef, bool]] = []

    def resolve(self, ref: AgentModelRef, *, require_tools: bool = True) -> BaseChatModel:
        self.calls.append((ref, require_tools))
        return self._model
