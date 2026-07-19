"""Predefined tool registry — capabilities → tools (ARCHITECTURE.md §10.5.4 / §12).

An agent's tool list is *assembled*, not hard-coded: each enabled capability
(§10.5.4) contributes one or more predefined tools. This registry is the seam
where those tools are produced. Builders are **injected** rather than imported so
that tools needing infrastructure that lands in a later build step — notably
``search_knowledge`` (RAG), which needs the pgvector retriever from Step 7 — are
registered by the composition root once their backing exists, without this module
importing the world.

Design (R2/R5):
* The set of valid capability keys is derived from :class:`Capabilities`, so the
  registry can never register a typo'd capability.
* Enabling a capability whose builder is not yet registered is **logged and
  skipped**, not silently ignored and not crashed — the agent simply runs without
  that tool until the backing step wires it. (A skip is visible in logs; it is not
  an error-swallowing band-aid because nothing failed — the tool just isn't
  available yet.)
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from langchain_core.tools import BaseTool

from app.agents.config import AgentConfig, Capabilities

logger = logging.getLogger(__name__)

# A builder turns an agent's config into the concrete tool(s) for one capability.
# It takes the whole config because tools are tenant-/agent-scoped (e.g. the
# knowledge retriever filters by team_id/agent_id, ARCH §10.5.2).
ToolBuilder = Callable[[AgentConfig], Sequence[BaseTool]]

# Valid capability keys = the Capabilities fields (single source of truth).
_VALID_CAPABILITIES: frozenset[str] = frozenset(Capabilities.model_fields)


class UnknownCapability(ValueError):
    """A builder was registered for a capability that is not a Capabilities field."""


class ToolRegistry:
    """Maps capability keys to tool builders and assembles an agent's tools."""

    def __init__(self) -> None:
        self._builders: dict[str, ToolBuilder] = {}

    def register(self, capability: str, builder: ToolBuilder) -> None:
        """Register the builder for one capability (overwrites a prior one).

        Raises:
            UnknownCapability: ``capability`` is not a :class:`Capabilities` field.
        """
        if capability not in _VALID_CAPABILITIES:
            raise UnknownCapability(
                f"{capability!r} is not a known capability; valid: {sorted(_VALID_CAPABILITIES)}"
            )
        self._builders[capability] = builder

    def assemble(self, cfg: AgentConfig) -> list[BaseTool]:
        """Build the full predefined-tool list for ``cfg``'s enabled capabilities.

        Capabilities with no registered builder are logged and skipped (see module
        docstring). Order follows :meth:`Capabilities.enabled` (declaration order)
        for deterministic agent construction + caching.
        """
        tools: list[BaseTool] = []
        for capability in cfg.capabilities.enabled():
            builder = self._builders.get(capability)
            if builder is None:
                logger.warning(
                    "agent %s enables capability %r but no tool builder is registered "
                    "(wired in a later build step); skipping",
                    cfg.id,
                    capability,
                )
                continue
            tools.extend(builder(cfg))
        return tools
