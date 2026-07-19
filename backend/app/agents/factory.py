"""Agent Factory — config → a real ReAct agent (ARCHITECTURE.md §22.2).

This is the load-bearing piece of Step 4: it turns an :class:`AgentConfig` into a
runnable peer agent built from real framework primitives only (CLAUDE R2).

Primitive choice (R1-verified, user-confirmed): we use ``deepagents.create_deep_agent``,
which *internally* builds a ``langchain.agents.create_agent`` ReAct agent and
auto-wires the deepagents stack — ``SkillsMiddleware`` (§26), ``FilesystemMiddleware``
+ ``MemoryMiddleware`` (§10), and summarization (§10.3). This satisfies both locked
decisions (create_agent ReAct agents *and* deepagents skills+memory) without
hand-rolling any middleware, which R2 forbids. Verified against deepagents 0.6.10:
``create_deep_agent(model, tools, *, system_prompt, skills, memory, backend, store,
response_format, checkpointer)``.

What the factory assembles (§22.4):
* **model** — resolved through the Model Resolution Layer with the tool-calling
  hard gate on (``require_tools=True``, §9.3). Mesh agents must call tools.
* **tools** — the predefined registry's tools for the agent's enabled capabilities
  (§10.5.4).
* **system_prompt** — the static persona + output contract (§22.2; the per-round
  blackboard is passed at invoke time by the runtime).
* **skills** — ordered filesystem-base→uploaded source paths (§26.3).
* **memory** — the ``/memories/`` StoreBackend mounted iff ``memory_enabled`` (§10.1).
* **response_format** — :class:`ContributionOut` bound through an explicit
  :class:`~langchain.agents.structured_output.ToolStrategy`, so every turn yields a
  typed, scorable result (§22.3) via a **tool call** on every provider.

Why ``ToolStrategy`` explicitly (R3 root-cause, not a patch): passing the bare
``ContributionOut`` schema lets ``create_agent`` wrap it in ``AutoStrategy``, which
selects the provider's *native* structured output (``ProviderStrategy``) for any
model whose profile advertises it. Native mode parses the model's final **text**
as JSON; when a tool-using agent ends a turn with empty assistant content, that
parse raises ``Expecting value: line 1 column 1 (char 0)`` and the whole turn
degrades to a confidence-0 abstention. The rest of this codebase is already built
around the tool-call path (the ``ContributionOut`` exit tool is filtered out of the
transparency ``tool_calls`` in :mod:`app.agents.runtime`), so we pin
``ToolStrategy`` here to make that the contract on every provider. ``ToolStrategy``
also defaults ``handle_errors=True``, so a malformed argument set is retried with a
correction message instead of crashing the round.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from deepagents import create_deep_agent
from deepagents.backends import (
    BackendProtocol,
    CompositeBackend,
    FilesystemBackend,
    StateBackend,
    StoreBackend,
)
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from app.agents.config import AgentConfig
from app.agents.contribution import ContributionOut
from app.agents.prompts import render_persona_prompt
from app.knowledge.metadata import CONVERSATION_TOOL_NAME, KNOWLEDGE_TOOL_NAME
from app.memory.namespaces import AGENTS_MEMORY_FILE, make_namespace_factory
from app.models_layer.resolver import AgentModelRef
from app.skills.loader import resolve_skill_sources
from app.tools.registry import ToolRegistry


class AgentBuildError(RuntimeError):
    """An agent config cannot be assembled into a runnable agent."""


class ModelProvider(Protocol):
    """The slice of the Model Resolution Layer the factory needs (§9.1).

    :class:`~app.models_layer.resolver.ModelResolver` satisfies this; tests inject
    a fake provider so the factory can be exercised with a scripted chat model
    (no live provider/secret needed).
    """

    def resolve(self, ref: AgentModelRef, *, require_tools: bool = True) -> BaseChatModel: ...


@dataclass(frozen=True)
class AgentFactory:
    """Builds peer ReAct agents from configs (§22.2).

    Args:
        models: the Model Resolution Layer (or a fake in tests).
        tools: the predefined tool registry (§10.5.4).
        store: the LangGraph Store for long-term memory; required only when an
            agent has ``memory_enabled``.
        base_skills_dir: host directory serving filesystem **base** skills (§26.3).
            Optional; uploaded skills (store-backed) are wired in Step 7.
        extra_tools: run-scoped tools appended to **every** agent this factory builds,
            independent of capabilities — used for the per-turn conversation-attachment
            retriever (``search_uploaded_files``, ARCH §8.5.3 / Bug 2).
    """

    models: ModelProvider
    tools: ToolRegistry
    store: BaseStore | None = None
    base_skills_dir: Path | None = None
    extra_tools: tuple[BaseTool, ...] = ()

    def build(self, cfg: AgentConfig) -> CompiledStateGraph[Any, Any, Any, Any]:
        """Build one runnable ReAct agent for ``cfg``.

        Raises:
            ModelNotToolCapable: the resolved model fails the tool-calling gate (§9.3).
            AgentBuildError: memory/skills are requested without their backing.
        """
        model = self.model_for(cfg)
        # Capability tools (per-cfg) + run-scoped extra tools (every agent), e.g. the
        # per-turn conversation-attachment retriever (Bug 2, §8.5.3).
        tools = [*self.tools.assemble(cfg), *self.extra_tools]
        skills = resolve_skill_sources(cfg.skill_sources) or None
        backend, memory_files = self._backend_and_memory(cfg)

        # Prompt hints are gated on each tool *actually* being attached (not on a config
        # flag), so we never tell a model about a tool it cannot call (Bug 1 / §10.5.2,
        # Bug 2 / §8.5.3).
        has_knowledge_tool = any(t.name == KNOWLEDGE_TOOL_NAME for t in tools)
        has_attachments_tool = any(t.name == CONVERSATION_TOOL_NAME for t in tools)

        return create_deep_agent(
            model=model,
            tools=tools,
            system_prompt=render_persona_prompt(
                cfg,
                has_knowledge_tool=has_knowledge_tool,
                has_attachments_tool=has_attachments_tool,
            ),
            skills=skills,
            memory=memory_files,
            backend=backend,
            store=self.store if memory_files else None,
            # Pin the tool-call strategy explicitly (see module docstring): never let
            # AutoStrategy fall back to the provider's native JSON mode, which crashes
            # the turn on empty assistant content.
            response_format=ToolStrategy(ContributionOut),
        )

    def model_for(self, cfg: AgentConfig) -> BaseChatModel:
        """Resolve this agent's chat model with the §9.3 tool-calling gate.

        Exposed (not just inlined in :meth:`build`) so callers that need the raw
        model — notably the mesh runner's structured-output repair fallback
        (:func:`app.agents.runtime.make_structured_repair`) — share the *exact*
        resolution the built agent uses.
        """
        return self.models.resolve(cfg.model_ref(), require_tools=True)

    def _backend_and_memory(
        self, cfg: AgentConfig
    ) -> tuple[BackendProtocol | None, list[str] | None]:
        """Compose the filesystem/store backend and memory file list (§10.1 / §26.3).

        * Filesystem **base** skills are served by a ``FilesystemBackend`` rooted at
          ``base_skills_dir`` (when provided).
        * Long-term memory mounts a ``StoreBackend`` at ``/memories/`` via a
          ``CompositeBackend`` route, namespaced per (team, agent) (§25.1).
        * With neither, ``backend=None`` lets deepagents default to ``StateBackend``.
        """
        has_uploaded = any(s.origin == "uploaded" for s in cfg.skill_sources)
        if has_uploaded and self.store is None:
            # Fail fast (R3): uploaded skills are store-backed; their full wiring is Step 7.
            raise AgentBuildError(
                f"agent {cfg.id} has uploaded skills but no store is configured "
                "(store-backed uploaded skills are wired in Step 7)"
            )

        # virtual_mode=True is required here for two reasons (verified deepagents 0.6.10):
        #   1) Security/§26.4 — it confines paths to root_dir; the default (False)
        #      lets absolute paths and `..` escape root, which we must not allow for
        #      (untrusted) skills. Defense-in-depth on top of the loader's validation.
        #   2) Correctness — CompositeBackend routing needs virtual path semantics.
        default_backend: BackendProtocol = (
            FilesystemBackend(root_dir=str(self.base_skills_dir), virtual_mode=True)
            if self.base_skills_dir is not None
            else StateBackend()
        )

        routes: dict[str, BackendProtocol] = {}
        memory_files: list[str] | None = None
        if cfg.memory_enabled:
            if self.store is None:
                raise AgentBuildError(
                    f"agent {cfg.id} has memory_enabled but no store is configured"
                )
            routes["/memories/"] = StoreBackend(
                store=self.store,
                namespace=make_namespace_factory(cfg.org_id, cfg.team_id, cfg.id),
            )
            memory_files = [AGENTS_MEMORY_FILE]

        if not routes and self.base_skills_dir is None:
            return None, None  # deepagents defaults to StateBackend()
        if not routes:
            return default_backend, None
        return CompositeBackend(default=default_backend, routes=routes), memory_files
