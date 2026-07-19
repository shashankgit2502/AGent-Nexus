"""HITL gate node — human review before synthesis (ARCHITECTURE.md §4.5 / §12).

LOCKED (CLAUDE.md §3): HITL is realised with the LangGraph ``interrupt()``
primitive *at this graph node* (the node-level form of the locked
"``HumanInTheLoopMiddleware`` / ``interrupt()``" decision). State persists via the
checkpointer so the run resumes on the same ``thread_id`` — proven across a
process restart in ``tests/graph/test_build.py``.

Why ``interrupt()`` and not ``HumanInTheLoopMiddleware`` here
------------------------------------------------------------
``HumanInTheLoopMiddleware`` (verified against langchain 1.3.9 via the LangChain
docs MCP) is *agent* middleware: it attaches to a ``create_agent`` and gates the
agent's **tool calls** (``interrupt_on={tool_name: ...}``). This gate is a **plain
graph node** before a synthesizer that is explicitly *not* an agent (locked) — so
there is no agent and no tool call for the middleware to wrap. The correct
primitive for pausing a graph node for human review is ``interrupt()`` +
``Command(resume=...)``. The same approve/edit/reject decision vocabulary is
preserved, so the contract matches what the middleware would expose.

Resume semantics (important)
----------------------------
When ``interrupt()`` pauses the run, LangGraph persists the checkpoint and raises;
on ``Command(resume=value)`` the node **re-executes from the top** and
``interrupt()`` returns ``value`` instead of pausing. Therefore the only code
before ``interrupt()`` is the cheap, idempotent construction of the review
payload — that payload is the AG-UI ``hitl_request`` content (emitted by the
streaming layer in Step 8 from the ``__interrupt__`` value). The ``hitl_resolved``
event is emitted from this node's *return*, which commits only after resume
(matching the run sequence in ARCH §21.4).
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.types import interrupt

from app.graph.state import CollabState, HITLDecision, make_event

logger = logging.getLogger(__name__)

# The decisions this gate offers on the converged candidate (ARCH §4.5). Mirrors
# the decision vocabulary HumanInTheLoopMiddleware would expose for a tool call.
ALLOWED_DECISIONS: tuple[str, ...] = ("approve", "edit", "reject")


def normalize_hitl_decision(raw: Any) -> HITLDecision:
    """Coerce a resume value into a typed :class:`HITLDecision` (validate at the seam, R5).

    Accepts the convenient bare-string forms (``"approve"`` / ``"reject"`` /
    ``"edit"``) and the structured dict forms (``{"type": "edit", "content": ...}``,
    ``{"type": "reject", "reason": ...}``). An unrecognised value fails **safe** to
    ``approve`` (the consensus already selected this candidate) with a warning —
    never silently, so a malformed client decision is visible in the logs (R3).
    """
    if isinstance(raw, str):
        raw = {"type": raw}

    if not isinstance(raw, dict) or raw.get("type") not in ALLOWED_DECISIONS:
        logger.warning("HITL: unrecognised decision %r; failing safe to 'approve'", raw)
        return {"type": "approve", "source": "human"}

    decision: HITLDecision = {"type": raw["type"], "source": "human"}
    if decision["type"] == "edit":
        content = raw.get("content")
        if not isinstance(content, str) or not content.strip():
            # "edit" with no replacement text is meaningless → treat as approve.
            logger.warning("HITL: 'edit' decision without content; treating as 'approve'")
            return {"type": "approve", "source": "human"}
        decision["content"] = content
    elif decision["type"] == "reject":
        reason = raw.get("reason")
        if isinstance(reason, str) and reason.strip():
            decision["reason"] = reason
    return decision


def _review_payload(state: CollabState) -> dict[str, Any]:
    """Build the human review payload (the AG-UI ``hitl_request`` content, §24.4)."""
    ranking = state["consensus_ranking"]
    top_key = ranking[0] if ranking else None
    candidate = None
    if top_key is not None:
        for contribution in state["contributions"]:
            if f"{contribution['agent_id']}:{contribution['round']}" == top_key:
                candidate = contribution["content"]
                break
    return {
        "type": "hitl_request",
        "candidate": candidate,
        "candidate_key": top_key,
        "ranking": ranking,
        "converged": state["converged"],
        "allowed_decisions": list(ALLOWED_DECISIONS),
    }


def hitl_node(state: CollabState) -> dict[str, Any]:
    """Pause for a human decision, or auto-approve in the lightweight path.

    Returns the resolved :class:`HITLDecision` on ``hitl_decision`` (read by the
    synthesizer and end nodes) plus a ``hitl_resolved`` event.
    """
    if not state["hitl_enabled"]:
        # ARCH §8.5 lightweight path: no human in the loop, accept consensus.
        decision: HITLDecision = {"type": "approve", "source": "auto"}
        return {
            "status": "hitl",
            "hitl_decision": decision,
            "events": [make_event("hitl_resolved", decision=decision["type"], source="auto")],
        }

    # Cheap + idempotent (re-runs on resume): build payload, then pause. The value
    # passed to interrupt() is surfaced to the client as the review request.
    raw = interrupt(_review_payload(state))
    decision = normalize_hitl_decision(raw)

    return {
        "status": "hitl",
        "hitl_decision": decision,
        "events": [make_event("hitl_resolved", decision=decision["type"], source="human")],
    }
