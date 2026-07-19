"""Prompt rendering for mesh agents (ARCHITECTURE.md §22.2).

Two seams, deliberately split:

* :func:`render_persona_prompt` — the **static** system prompt (persona + the
  output contract). It does not change between rounds, so the factory bakes it
  into the compiled agent once and the resolved model stays cacheable (§27.4).
* :func:`render_round_message` — the **per-round** human message carrying the
  current blackboard slice (goal, this agent's framing, peers' latest work). This
  is what makes each round's invocation read "the whole blackboard" (§2.1) while
  the agent object itself is reused.

Keeping the volatile blackboard out of ``system_prompt`` is the practical reading
of ARCH §22.2's "build per turn or cached": persona is cached, blackboard is
passed in per turn.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.agents.config import AgentConfig
from app.graph.state import Contribution, Critique, previous_round_contributions

_OUTPUT_CONTRACT = (
    "You MUST finish your turn by calling the `ContributionOut` tool — that tool "
    "call IS your answer for the round. Do NOT reply with a plain-text message "
    "instead; a turn that ends without calling `ContributionOut` is discarded and "
    "counts as an abstention. When you have reasoned (and used any tools you need), "
    "call it exactly once with:\n"
    "  - content: your proposal/answer for THIS round, standalone and concrete.\n"
    "  - confidence: your honest 0.0–1.0 self-assessment (used in the team's "
    "confidence-weighted vote — do not inflate it).\n"
    "  - responds_to: agent_ids of the specific peers whose prior-round work you "
    "directly build on or answer (empty in the opening round).\n"
    "  - critiques: optional, targeted critiques of specific peers' prior-round "
    "contributions (target_agent + severity + content)."
)

# Only injected when the agent actually has the `search_knowledge` tool attached
# (its RAG capability is enabled AND the team's knowledge store resolved). Telling a
# model about a tool it cannot call would invite hallucinated tool calls, so the
# factory passes ``has_knowledge_tool`` reflecting the *assembled* tool list, not just
# the config flag (Bug 1, ARCH §10.5.2 checklist #4).
_KNOWLEDGE_HINT = (
    "You have access to your team's shared knowledge base and your own private "
    "sources via the `search_knowledge` tool. When the goal may relate to uploaded "
    "documents or reference material, call `search_knowledge(query)` to retrieve "
    "relevant passages and ground your contribution in them rather than guessing.\n\n"
)

# Injected only when the conversation has uploaded files AND the per-turn attachment
# tool is actually attached (Bug 2, ARCH §8.5.3) — same guard rationale as the
# knowledge hint: never advertise a tool the agent cannot call.
_ATTACHMENTS_HINT = (
    "The user has attached one or more files to THIS conversation. Use the "
    "`search_uploaded_files` tool to read them: call `search_uploaded_files(query)` "
    "to retrieve relevant passages from the uploaded documents and base your answer "
    "on them when the question refers to an attachment.\n\n"
)


def render_persona_prompt(
    cfg: AgentConfig,
    *,
    has_knowledge_tool: bool = False,
    has_attachments_tool: bool = False,
) -> str:
    """Build the static system prompt: persona + (optional) tool hints + contract.

    Args:
        cfg: the agent's config (persona body).
        has_knowledge_tool: whether ``search_knowledge`` is actually in the agent's
            assembled tool list (§10.5.2). The factory computes this from the built
            tools so the prompt never advertises a tool the agent does not have.
        has_attachments_tool: whether the per-turn ``search_uploaded_files`` tool is
            attached for this conversation (§8.5.3) — same never-advertise-an-absent-
            tool guard.
    """
    persona = (
        cfg.instructions.strip() or f"You are '{cfg.name}', a peer agent on a collaborating team."
    )
    knowledge_block = _KNOWLEDGE_HINT if has_knowledge_tool else ""
    attachments_block = _ATTACHMENTS_HINT if has_attachments_tool else ""
    return (
        f"{persona}\n\n"
        "You are one peer in a decentralized team of agents collaborating over a "
        "shared blackboard. There is no manager: read your peers' contributions, "
        "build on or challenge them, and converge the team toward the goal.\n\n"
        f"{knowledge_block}"
        f"{attachments_block}"
        f"{_OUTPUT_CONTRACT}"
    )


def _format_contributions(contributions: list[Contribution], *, self_id: str) -> str:
    if not contributions:
        return "(no peer contributions yet — this is the opening round)"
    lines: list[str] = []
    for c in contributions:
        who = "you" if c["agent_id"] == self_id else c["agent_id"]
        lines.append(f"- [{who}] (confidence {c['confidence']:.2f}) {c['content']}")
    return "\n".join(lines)


def _format_critiques(critiques: list[Critique], *, self_id: str) -> str:
    relevant = [c for c in critiques if c["target_agent"] == self_id]
    if not relevant:
        return ""
    lines = [f"- from {c['from_agent']} ({c['severity']}): {c['content']}" for c in relevant]
    return "\n\nCritiques aimed at your previous contribution:\n" + "\n".join(lines)


def render_round_message(cfg: AgentConfig, blackboard: Mapping[str, Any]) -> str:
    """Build the per-round human message from the current blackboard slice.

    Surfaces the **previous** round's peer contributions, not the current one.

    Root cause this corrects (R3): during the ``Send()`` fan-out for round N the
    blackboard's ``round`` is N, but round-N contributions don't exist yet — every
    peer is producing them in parallel this super-step (ARCH §23.4, "eventually
    visible next round"). Reading round N would therefore show an empty list and
    every round-≥2 agent would be told "this is the opening round", blinding the
    mesh to prior work and defeating "emergence through iteration" (ARCH §2.3).
    The peers' latest *visible* contributions are round N-1, so we render those.

    Args:
        cfg: this agent's config (for its id + tailored framing).
        blackboard: the ``CollabState`` slice delivered to the turn (goal,
            success criteria, contributions, critiques, round).
    """
    self_id = str(cfg.id)
    goal = blackboard.get("goal", "")
    criteria = blackboard.get("success_criteria") or []
    framing = (blackboard.get("agent_task_framing") or {}).get(self_id, "")
    current_round = blackboard.get("round", 1)
    peers = previous_round_contributions(blackboard)

    criteria_block = (
        "Success criteria:\n" + "\n".join(f"  - {c}" for c in criteria)
        if criteria
        else "Success criteria: (none specified)"
    )
    framing_block = f"\n\nYour task framing: {framing}" if framing else ""

    return (
        f"Team goal: {goal}\n"
        f"{criteria_block}{framing_block}\n\n"
        f"Round {current_round}. Latest contributions on the blackboard:\n"
        f"{_format_contributions(peers, self_id=self_id)}"
        f"{_format_critiques(list(blackboard.get('critiques') or []), self_id=self_id)}\n\n"
        "Produce your contribution for this round."
    )
