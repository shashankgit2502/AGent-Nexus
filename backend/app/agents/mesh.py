"""Production mesh runner — agent_id → real ReAct turn (ARCHITECTURE.md §22).

This is the composition root that satisfies :class:`~app.graph.context.MeshRunner`
for a real run: it looks up the agent's config, builds the agent through the
factory (Step 4), and runs one turn (Step 4 runtime), mapping the result onto the
additive blackboard channels (ARCH §6).

It is deliberately thin glue — every load-bearing piece is a real primitive built
in earlier steps (R2): the repository, the :class:`~app.agents.factory.AgentFactory`
(which wraps ``deepagents.create_deep_agent``), and ``run_agent_turn``. The graph
node (``agent_turn``) holds none of this; it only calls ``runner.run(...)`` through
the injected runtime context, which keeps the node testable and the agent stack
out of the checkpointed state.

Build-vs-cache note (ARCH §22.2 / NFR-2): we build the agent per turn here. Caching
resolved agents by ``(catalog_id, profile_id)`` is a later optimisation; correctness
of the mesh round does not depend on it, so it is intentionally deferred.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.agents.config import AgentRepository
from app.agents.factory import AgentFactory
from app.agents.runtime import (
    arun_agent_turn,
    astream_agent_turn,
    make_structured_repair,
    run_agent_turn,
)
from app.graph.context import EmitFn


@dataclass(frozen=True)
class FactoryMeshRunner:
    """Resolve an ``agent_id`` to a config, build it, and run its round.

    Args:
        factory: builds a runnable ReAct agent from an :class:`AgentConfig` (§22.2).
        repo: read access to agent configs by id (the agents are spawned from
            their stored config at run time, §22.1).
    """

    factory: AgentFactory
    repo: AgentRepository

    def run(self, agent_id: str, blackboard: Mapping[str, Any]) -> dict[str, Any]:
        """Run one peer agent's turn for the current round.

        ``agent_id`` arrives as a string on the blackboard (it is also a
        ``CollabState.active_agent_ids`` entry); the repository is keyed by
        ``UUID``, so we parse it here at the boundary (R5: validate at the seam).
        """
        cfg = self.repo.get(UUID(agent_id))
        agent = self.factory.build(cfg)
        # Pass a structured-output repair built from the SAME resolved model, so a
        # turn that ends without calling ContributionOut is salvaged into a real
        # typed contribution instead of being discarded as an abstention (§21.5).
        repair = make_structured_repair(self.factory.model_for(cfg))
        return run_agent_turn(agent, cfg, blackboard, repair=repair)

    async def arun(
        self, agent_id: str, blackboard: Mapping[str, Any], *, emit: EmitFn, live: bool = True
    ) -> dict[str, Any]:
        """Run one peer agent's turn asynchronously.

        Same resolution as :meth:`run` (config → build → repair). With ``live=True``
        it drives the agent through :func:`~app.agents.runtime.astream_agent_turn`,
        emitting reasoning / tool_call / tool_result events through ``emit`` as they
        happen (Bug 5). With ``live=False`` it runs non-streaming
        (:func:`~app.agents.runtime.arun_agent_turn`) so a provider that repeats
        tool-call names across stream chunks can't corrupt them (the doubled-name
        bug, ``AGENT_LIVE_STREAMING``); the trajectory's events are projected
        post-hoc into the returned update instead.
        """
        cfg = self.repo.get(UUID(agent_id))
        agent = self.factory.build(cfg)
        repair = make_structured_repair(self.factory.model_for(cfg))
        if live:
            return await astream_agent_turn(agent, cfg, blackboard, emit=emit, repair=repair)
        return await arun_agent_turn(agent, cfg, blackboard, repair=repair)
