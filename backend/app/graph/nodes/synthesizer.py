"""Synthesizer node — merge the consensus result into one output (ARCH §4.6).

LOCKED (CLAUDE.md §3): the Synthesizer is a **plain LangGraph node, not an
agent**, and may run on a cheaper non-tool model. It merges the
consensus-selected contributions into the final artifact.

It honours the human's HITL decision (ARCH §4.5), read from ``hitl_decision``:

* **approve** — merge the ranked contributions into ``final_output``. The merge
  uses the injected :class:`~app.graph.context.Synthesizer` (a real cheaper-model
  call) when present; otherwise it falls back to the deterministic top-ranked
  contribution so the graph still runs without a model (foundation/mesh tests).
* **edit** — the human authored the answer; use their ``content`` verbatim (do
  not re-synthesise over a human edit).
* **reject** — produce no output; ``final_output`` stays ``None`` and the end node
  records a rejected artifact.

The injected synthesizer keeps this node thin and testable (same DI pattern as the
mesh ``runner``); model resolution lives at the composition root (Step 9).
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.runtime import Runtime

from app.graph.context import MeshContext
from app.graph.state import CollabState, make_event, ranked_contributions, text_block

logger = logging.getLogger(__name__)


def _fallback_merge(state: CollabState) -> str:
    """Deterministic top-ranked pick when no model synthesizer is injected.

    This is the foundation/mesh-test behaviour: the highest-confidence
    contribution's content stands in for a real merge.
    """
    ranked = ranked_contributions(state)
    if ranked:
        return ranked[0]["content"]
    return "[no contributions to synthesize]"


def _decide(
    state: CollabState, runtime: Runtime[MeshContext]
) -> tuple[str | None, list[dict[str, Any]]]:
    """Resolve ``(final_output, synthesis_events)`` per the human decision + ranking.

    Shared by the sync and async synthesizer nodes. ``final_output`` is ``None`` only
    on **reject** (the producer is then skipped — there is nothing agreed to build a
    file from, §2A).
    """
    decision = state["hitl_decision"] or {"type": "approve"}
    dtype = decision["type"]

    if dtype == "reject":
        # Human rejected the converged result — synthesise nothing (ARCH §4.5).
        return None, [make_event("synthesis", rejected=True)]

    if dtype == "edit" and decision.get("content"):
        final_output = decision["content"]
        return final_output, [
            make_event("synthesis", source="human_edit", content_blocks=[text_block(final_output)])
        ]

    # approve → merge the ranked contributions.
    synthesizer = runtime.context.synthesizer if runtime.context is not None else None
    if synthesizer is None:
        final_output = _fallback_merge(state)
        source = "fallback"
    else:
        final_output = synthesizer.synthesize(
            goal=state["goal"],
            success_criteria=state["success_criteria"],
            ranked=ranked_contributions(state),
        )
        source = "model"

    return final_output, [
        make_event(
            "synthesis",
            source=source,
            ranking=state["consensus_ranking"],
            content_blocks=[text_block(final_output)],
        )
    ]


def synthesizer_node(state: CollabState, runtime: Runtime[MeshContext]) -> dict[str, Any]:
    """Produce ``final_output`` per the human decision and consensus ranking (sync).

    The sync path is the foundation/mesh-test entrypoint (no producer): real runs go
    through :func:`asynthesizer_node`, which additionally invokes the post-consensus
    artifact producer (the producer needs ``await`` — DB + an agent turn).
    """
    final_output, events = _decide(state, runtime)
    return {"final_output": final_output, "status": "synth", "events": events}


async def asynthesizer_node(
    state: CollabState, runtime: Runtime[MeshContext]
) -> dict[str, Any]:
    """Synthesize, then run the post-consensus artifact producer if one is wired (§2A).

    Production happens **after** the prose ``final_output`` exists and **only** when a
    producer is injected and there is an agreed result (skipped on reject). The
    producer's ``tool_result`` events are appended *after* the ``synthesis`` event so
    they stream in order, before ``run_finished`` (§11.3). The control graph shape is
    unchanged — the producer is a sub-step of synthesis, not a new node (§2A).
    """
    final_output, events = _decide(state, runtime)

    producer = runtime.context.producer if runtime.context is not None else None
    if producer is not None and final_output:
        producer_events = await producer.produce(
            goal=state["goal"],
            success_criteria=state["success_criteria"],
            final_output=final_output,
            ranked=ranked_contributions(state),
        )
        events = [*events, *(dict(e) for e in producer_events)]

    return {"final_output": final_output, "status": "synth", "events": events}
