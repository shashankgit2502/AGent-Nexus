"""Runtime context for the collaboration graph (ARCHITECTURE.md §7 / §22).

The mesh ``agent_turn`` node needs a dependency it cannot read from the
blackboard state: *how to actually run an agent's turn* (resolve its model, build
the ReAct agent, invoke it). That is a runtime dependency, not domain state, so we
inject it the LangGraph-idiomatic way — **Runtime context** (R1-verified against
langgraph 1.2.5 via the LangChain docs MCP):

    graph = StateGraph(CollabState, context_schema=MeshContext)
    graph.invoke(state, config, context=MeshContext(runner=...))

    def agent_turn_node(payload, runtime: Runtime[MeshContext]): ...

Keeping it out of ``CollabState`` matters: the blackboard is checkpointed and
parallel-merged, and a live ``AgentFactory``/repository is neither serialisable
nor something we want in the persisted state. Runtime context is the framework's
dependency-injection seam (LangGraph "static runtime context").

The ``runner`` is **optional**: when no context is supplied (e.g. the foundation
checkpoint/resume tests), ``runtime.context`` is ``None`` and the node falls back
to its deterministic stub. A real run passes a :class:`MeshRunner`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

# An async sink for one raw AG-UI event record (``{type, data}``). The run's
# :class:`~app.streaming.emitter.RunEventEmitter.emit` satisfies it; threading it
# into the runtime context lets the mesh node stream an agent's reasoning / tool
# calls **live**, as they happen, instead of projecting them post-hoc (Bug 5).
EmitFn = Callable[[Mapping[str, Any]], Awaitable[Any]]


@runtime_checkable
class MeshRunner(Protocol):
    """Runs one peer agent's round and returns an additive blackboard update.

    The single seam between the graph and the agent layer: given an ``agent_id``
    and the current blackboard slice, produce ``{"contributions": [...],
    "critiques": [...], "events": [...]}`` (the additive channels, ARCH §6). The
    production implementation is
    :class:`~app.agents.mesh.FactoryMeshRunner`; tests may supply any object
    satisfying this Protocol.

    ``run`` is the synchronous turn (post-hoc event projection); ``arun`` is the
    async turn. With ``live=True`` it streams the agent's trajectory, emitting
    reasoning / tool_call / tool_result events **live** through ``emit`` as they
    occur (Bug 5) — the activity events are then *not* in the returned update, only
    the round-cadenced ``contribution`` / ``critique``. With ``live=False`` (the
    default for correctness, see ``AGENT_LIVE_STREAMING``) it runs non-streaming
    (``ainvoke``) so tool-call names are never corrupted by a provider that repeats
    them across stream chunks, and returns ALL events (reasoning/tool/contribution/
    critique) in the update for the run streamer to emit post-hoc.
    """

    def run(self, agent_id: str, blackboard: Mapping[str, Any]) -> dict[str, Any]: ...

    async def arun(
        self, agent_id: str, blackboard: Mapping[str, Any], *, emit: EmitFn, live: bool = True
    ) -> dict[str, Any]: ...


@runtime_checkable
class Synthesizer(Protocol):
    """Merges the consensus-ranked contributions into one final output (ARCH §4.6).

    The second injected seam (alongside :class:`MeshRunner`). Keeping it out of
    the node lets the synthesizer run a real *cheaper non-tool model* (locked
    decision, CLAUDE.md §3) at the composition root while the node stays a thin,
    testable plain node. ``synthesizer=None`` selects the deterministic top-ranked
    fallback so the foundation/mesh tests run without a model. The production
    implementation is :class:`~app.synthesis.synthesizer.LLMSynthesizer`.
    """

    def synthesize(
        self, *, goal: str, success_criteria: list[str], ranked: Sequence[Mapping[str, Any]]
    ) -> str: ...


@runtime_checkable
class ArtifactProducer(Protocol):
    """Produces downloadable file artifacts from the consensus result (ARTIFACTS §2A).

    The fourth injected seam. Invoked as a post-consensus sub-step of the synthesizer
    node (keeping the locked control graph ``… → Synthesizer → End`` unchanged): given
    the agreed ``final_output`` + ranked contributions, it persists 0..N file artifacts
    and returns their ``tool_result`` events (§11.1) for the node to stream — after the
    ``synthesis`` event, before ``run_finished``. ``producer=None`` (foundation/mesh
    tests, or a team with no file-capable producer agent) skips production: the run is
    a prose answer only. The production implementation is
    :class:`~app.artifacts.producer.ArtifactAgentProducer`.
    """

    async def produce(
        self,
        *,
        goal: str,
        success_criteria: Sequence[str],
        final_output: str,
        ranked: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class Consolidator(Protocol):
    """Persists memory-enabled agents' contributions to long-term memory (ARCH §25.3).

    The third injected seam (Item 3 M2). Keeping it out of the node lets the post-run
    write run a real model + store at the composition root while the
    ``consolidation`` node stays a thin, testable plain node. ``consolidator=None``
    makes that node a no-op (foundation/mesh tests, or a team with no memory-enabled
    agents). The production implementation is
    :class:`~app.memory.consolidation.MemoryConsolidator`.
    """

    def consolidate_run(self, state: Mapping[str, Any]) -> Any: ...


@dataclass(frozen=True)
class MeshContext:
    """Static runtime context threaded to every node of one graph invocation.

    The mesh node reads ``runner``; the synthesizer node reads ``synthesizer`` +
    ``producer``; the consolidation node reads ``consolidator``. All default to
    ``None`` so the persistence-focused foundation tests keep running without an agent
    stack, a model, or a store.
    """

    runner: MeshRunner | None = None
    synthesizer: Synthesizer | None = None
    consolidator: Consolidator | None = None
    # The post-consensus artifact producer (ARTIFACTS §2A); read by the (async)
    # synthesizer node. ``None`` ⇒ prose-only run (no file deliverables).
    producer: ArtifactProducer | None = None
    # When present (real runs), the mesh node emits each agent's activity events
    # through this sink (Bug 5). ``None`` (foundation/mesh tests, sync invoke)
    # selects the post-hoc projection — identical to the prior behaviour.
    emit: EmitFn | None = None
    # Whether the async mesh turn streams its trajectory token-by-token (live) or
    # runs non-streaming and projects events post-hoc. Default ``False`` because
    # token streaming corrupts tool-call names on some OpenAI-compatible providers
    # (see ``AGENT_LIVE_STREAMING``); non-streaming is correct on every provider.
    live_streaming: bool = False
    # Provider-agnostic wall-clock bound for a single live agent turn (seconds); a
    # turn that exceeds it is cancelled and recorded as an abstention so one slow /
    # unresponsive model never freezes the round (§21.5). ``None`` = no bound.
    turn_timeout_s: float | None = None
