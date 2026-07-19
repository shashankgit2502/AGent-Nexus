"""``build_collab_graph`` — the outer control graph (ARCHITECTURE.md §7).

This compiles the locked control skeleton (CLAUDE.md §3):

    Orchestrator → Mesh Round ↺ Consensus → HITL → Synthesizer → End

The "DAG with a loop" is this skeleton; the loop is the debate rounds. The inner
mesh (no fixed flow) is produced by ``fan_out_to_mesh`` returning parallel
``Send()``s to ``agent_turn`` (ARCH §2.1).

In Step 2 the nodes are deterministic stubs; subsequent build-order steps replace
each body (real agents, consensus math already real, HITL middleware, synthesizer
model) without changing this wiring.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from langgraph.utils.runnable import RunnableCallable  # type: ignore[attr-defined]

from app.graph.context import MeshContext
from app.graph.nodes import (
    aagent_turn_node,
    agent_turn_node,
    asynthesizer_node,
    consensus_node,
    consolidation_node,
    end_node,
    hitl_node,
    orchestrator_node,
    synthesizer_node,
)
from app.graph.routing import fan_out_to_mesh, route_after_consensus
from app.graph.state import CollabState


def build_collab_graph(
    checkpointer: BaseCheckpointSaver[Any],
    store: BaseStore | None = None,
) -> CompiledStateGraph[CollabState, Any, CollabState, CollabState]:
    """Compile the collaboration graph with persistence attached.

    Args:
        checkpointer: short-term state persistence + HITL resume (ARCH §10);
            a ``PostgresSaver`` in production, an ``InMemorySaver`` in unit tests.
        store: long-term per-agent memory (ARCH §10). Optional in the foundation
            slice; wired to agents in Step 7.

    Returns:
        The compiled, runnable graph. Pass a :class:`MeshContext` with a
        ``runner`` at ``invoke(..., context=...)`` to run real agents; omit it and
        the mesh node falls back to its deterministic stub (foundation tests).
    """
    # `context_schema` injects non-state runtime dependencies (the mesh runner)
    # into nodes that ask for a `Runtime[MeshContext]` — the LangGraph
    # dependency-injection seam (R1-verified, langgraph 1.2.5). The blackboard
    # state stays free of the unserialisable agent stack.
    graph = StateGraph(CollabState, context_schema=MeshContext)

    graph.add_node("orchestrator", orchestrator_node)
    # `agent_turn_node` is reached only via Send() with a payload that is a
    # superset of the state (it carries `agent_id`), so it takes a Mapping rather
    # than CollabState. LangGraph's add_node stubs can't express a Send-only
    # node signature, hence the targeted ignore (runtime behaviour verified).
    #
    # Dual sync/async (Bug 5): a sync `invoke` (foundation/mesh tests) uses the
    # post-hoc `agent_turn_node`; an async `astream` (the real run path) uses
    # `aagent_turn_node`, which streams the agent's activity events live. Same node,
    # picked by the call style — verified against langgraph's RunnableCallable.
    graph.add_node(
        "agent_turn",
        RunnableCallable(agent_turn_node, aagent_turn_node),
    )
    graph.add_node("consensus", consensus_node)
    graph.add_node("hitl", hitl_node)
    # Dual sync/async (mirrors agent_turn): a sync `invoke` (foundation/mesh tests)
    # uses the producer-unaware `synthesizer_node`; an async `astream` (real runs)
    # uses `asynthesizer_node`, which runs the post-consensus artifact producer
    # (ARTIFACTS §2A) — it needs `await` (DB + a producer agent turn).
    graph.add_node(
        "synthesizer",
        RunnableCallable(synthesizer_node, asynthesizer_node),
    )
    graph.add_node("consolidation", consolidation_node)
    graph.add_node("end_node", end_node)

    graph.add_edge(START, "orchestrator")
    # Entry → inner mesh: parallel Send() fan-out to every active agent.
    graph.add_conditional_edges("orchestrator", fan_out_to_mesh, ["agent_turn"])
    # All parallel agent_turns join at consensus.
    graph.add_edge("agent_turn", "consensus")
    # Outer loop: another round, or proceed to the human gate.
    graph.add_conditional_edges("consensus", route_after_consensus, ["agent_turn", "hitl"])
    graph.add_edge("hitl", "synthesizer")
    # Post-run memory consolidation (Item 3 M2): after the answer exists, persist
    # each memory-enabled agent's durable learnings, then finalise. A no-op when no
    # consolidator is in the runtime context (foundation tests / no memory agents).
    graph.add_edge("synthesizer", "consolidation")
    graph.add_edge("consolidation", "end_node")
    graph.add_edge("end_node", END)

    return graph.compile(checkpointer=checkpointer, store=store)
