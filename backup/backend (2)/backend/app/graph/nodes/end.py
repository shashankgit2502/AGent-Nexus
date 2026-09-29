"""End node — finalise the run (ARCHITECTURE.md §4.7).

Assembles the final **artifact** from the synthesised output (or records a
rejected outcome when the human rejected at the HITL gate), emits the terminal
``run_finished`` AG-UI event carrying that artifact, and marks the run ``done``.

Scope note (R6): persisting the artifact as a row in the ``artifacts`` table
(TECHNICAL §11.4) happens at the composition/route layer in **Step 9**, once the
SQLAlchemy repositories exist. Here we build the artifact *record* and emit it on
the terminal event so the in-graph run is complete and the artifact is fully
formed for that later persistence — no DB coupling is introduced into the graph.
"""

from __future__ import annotations

from typing import Any

from app.graph.state import CollabState, make_event

# Artifact ``kind`` values (TECHNICAL §11.4 ``artifacts.kind`` is free TEXT; these
# are the two outcomes this node produces).
_KIND_SYNTHESIS = "synthesis"
_KIND_REJECTED = "rejected"

_REJECTED_NOTICE = "Run rejected by the human reviewer; no output was synthesised."


def _build_artifact(state: CollabState) -> dict[str, Any]:
    """Build the final artifact record (kind/content/content_format)."""
    decision = state["hitl_decision"]
    rejected = decision is not None and decision["type"] == "reject"

    if rejected:
        reason = decision.get("reason") if decision else None
        return {
            "kind": _KIND_REJECTED,
            "content": reason or _REJECTED_NOTICE,
            "content_format": "markdown",
        }

    return {
        "kind": _KIND_SYNTHESIS,
        "content": state["final_output"],
        "content_format": "markdown",
    }


def end_node(state: CollabState) -> dict[str, Any]:
    """Mark the run complete and emit the terminal event with the artifact."""
    artifact = _build_artifact(state)
    return {
        "status": "done",
        "events": [make_event("run_finished", artifact=artifact)],
    }
