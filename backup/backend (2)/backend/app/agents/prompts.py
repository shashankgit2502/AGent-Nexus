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

from app.a2a.limits import DEFAULT_LIMITS, A2ALimits
from app.a2a.messages import inbox_for
from app.a2a.render import render_inbox
from app.agents.config import AgentConfig
from app.graph.state import (
    Contribution,
    Critique,
    current_run_id,
    previous_round_contributions,
    run_critiques,
    run_messages,
)

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
    "contributions (target_agent + severity + content).\n"
    "  - messages: typed messages to your peers (see below). Empty if you have nothing "
    "to say to anyone."
)

# The A2A vocabulary (ARCH §23.3), taught in the STATIC system prompt rather than the
# per-round message. Two reasons: it belongs beside the output contract that already
# describes the other ContributionOut fields, and an opening-round agent must already know
# it can INFORM or PROPOSE — a round-1 agent has no inbox, so a vocabulary taught only
# alongside incoming mail would arrive one round too late to shape the first move.
_A2A_CONTRACT = (
    "\n\nTALKING TO YOUR TEAM (the `messages` field)\n"
    "You are not answering alone. Use these to work WITH your peers — each message needs "
    "an `intent`, a `to` (an agent_id, or '*' for the whole team), and a `body`:\n"
    "  - INFORM (broadcast): share a finding your peers can build on and CITE. Put the "
    "substance in the body and the URLs in source_urls, so nobody has to redo your work.\n"
    "  - REQUEST (to one peer): ask for something you actually need. If you are blocked "
    "on a peer's output, say so explicitly instead of guessing or stalling.\n"
    "  - PROPOSE (broadcast): put forward ONE piece of the solution — a structure, an "
    "approach, an outline — for others to fill in or challenge.\n"
    "  - DELEGATE (to one peer): hand over work you discovered but do not own. Use it "
    "when the right person for a task is clearly someone else.\n"
    "  - ENDORSE (to one peer): back a peer's work when you genuinely agree. This is how "
    "the team registers real agreement, as opposed to your own self-assessment.\n"
    "  - VOTE (to one peer): pick the single best peer contribution of the last round. "
    "You get ONE vote per round and you may not vote for yourself.\n"
    "  - CRITIQUE (to one peer): challenge specific reasoning (minor | major | blocking).\n"
    "Rules: you may not address yourself; you may only ENDORSE/VOTE/CRITIQUE a peer whose "
    "work you were actually shown; keep it to a few messages per round — say what matters, "
    "not everything. Your messages reach your peers NEXT round, so ask early."
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
        f"{_A2A_CONTRACT}"
    )


# Total characters the peers-contributions block may occupy, across ALL peers.
#
# Why a total and not just the per-peer cap: the per-peer cap is multiplied by the number of
# peers, so the block grows linearly with team size — at 12 agents, 11 peers × 1500 chars is
# ~16,500 characters (~4,100 tokens) in EVERY agent's prompt, EVERY round. That is a
# quadratic token bill in team size and the main reason large teams become unaffordable.
# Bounding the total keeps a 12-agent round costing about what a 5-agent round costs.
_PEER_BLOCK_MAX_CHARS = 6000

# Never shrink a peer below this: a contribution cut to a sentence is not worth its tokens,
# and dropping *peers* entirely would be a worse trade than showing each one more briefly.
_PEER_MIN_CHARS = 400


def _peer_budget(peer_count: int, configured_max: int) -> int:
    """Per-peer character cap that keeps the whole peers block bounded (any team size).

    Returns the smaller of the configured per-peer cap and an equal share of the block
    budget, floored so each peer stays readable. Small teams are unaffected — with 2 peers
    the share is 3000, well above the 1500 default, so the configured cap wins and behaviour
    is byte-identical to before. Only teams large enough to blow the budget are compressed.
    """
    if peer_count <= 0:
        return configured_max
    share = max(_PEER_MIN_CHARS, _PEER_BLOCK_MAX_CHARS // peer_count)
    if configured_max <= 0:  # 0 = "no cap" — honour it, but still bound the total.
        return share
    return min(configured_max, share)


def _truncate(text: str, max_chars: int) -> str:
    """Cap ``text`` at ``max_chars`` with an explicit marker (``0`` = no cap).

    Keeps the truncation visible so a peer's proposal is never *silently* shortened —
    the reader (and the model) can tell the gist was preserved but the tail dropped.
    """
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + " […truncated]"


def _format_contributions(
    contributions: list[Contribution], *, self_id: str, max_chars: int = 0
) -> str:
    if not contributions:
        return "(no peer contributions yet — this is the opening round)"
    lines: list[str] = []
    for c in contributions:
        who = "you" if c["agent_id"] == self_id else c["agent_id"]
        content = _truncate(c["content"], max_chars)
        lines.append(f"- [{who}] (confidence {c['confidence']:.2f}) {content}")
    return "\n".join(lines)


def _format_critiques(critiques: list[Critique], *, self_id: str) -> str:
    relevant = [c for c in critiques if c["target_agent"] == self_id]
    if not relevant:
        return ""
    lines = [f"- from {c['from_agent']} ({c['severity']}): {c['content']}" for c in relevant]
    return "\n\nCritiques aimed at your previous contribution:\n" + "\n".join(lines)


def render_round_message(
    cfg: AgentConfig,
    blackboard: Mapping[str, Any],
    *,
    limits: A2ALimits = DEFAULT_LIMITS,
) -> str:
    """Build the per-round human message from the current blackboard slice.

    Surfaces the **previous** round's peer contributions, not the current one.

    Root cause this corrects (R3): during the ``Send()`` fan-out for round N the
    blackboard's ``round`` is N, but round-N contributions don't exist yet — every
    peer is producing them in parallel this super-step (ARCH §23.4, "eventually
    visible next round"). Reading round N would therefore show an empty list and
    every round-≥2 agent would be told "this is the opening round", blinding the
    mesh to prior work and defeating "emergence through iteration" (ARCH §2.3).
    The peers' latest *visible* contributions are round N-1, so we render those.

    Also renders this agent's **inbox** — the messages peers addressed to it last round
    (ARCH §23.4/§23.5). This is the delivery half of the A2A contract: without it agents
    can emit a ``REQUEST`` that nobody ever reads. It is placed immediately before "produce
    your contribution" so the last thing the model sees before answering is what its team
    asked of it — the inbox/outbox rule that an agent processes its mail *before* acting on
    shared state.

    Args:
        cfg: this agent's config (for its id + tailored framing).
        blackboard: the ``CollabState`` slice delivered to the turn (goal,
            success criteria, contributions, critiques, messages, round).
        limits: §23.5 inbox budget. Defaults to the shipped values, so callers that do not
            inject settings render exactly the same bounded inbox.
    """
    self_id = str(cfg.id)
    goal = blackboard.get("goal", "")
    criteria = blackboard.get("success_criteria") or []
    framing = (blackboard.get("agent_task_framing") or {}).get(self_id, "")
    current_round = blackboard.get("round", 1)
    peers = previous_round_contributions(blackboard)
    # Per-peer length cap for rounds ≥ 2 (0 = no cap): shrinks each request so more
    # real work fits under the provider rate budget (ARCH §7 / config.py). Read off
    # the blackboard — a run-tuning parameter carried in state, no signature threading.
    # Adaptive: the configured per-peer cap, reduced if the team is large enough that the
    # peers block would otherwise dominate the prompt (see ``_peer_budget``).
    max_peer_chars = _peer_budget(len(peers), int(blackboard.get("peer_content_max_chars", 0) or 0))

    criteria_block = (
        "Success criteria:\n" + "\n".join(f"  - {c}" for c in criteria)
        if criteria
        else "Success criteria: (none specified)"
    )
    framing_block = f"\n\nYour task framing: {framing}" if framing else ""

    # The agent's mail: run-scoped, previous-round, priority-ordered, budget-bounded.
    inbox_block = render_inbox(
        inbox_for(
            run_messages(blackboard),
            agent_id=self_id,
            current_round=current_round,
            run_id=current_run_id(blackboard),
        ),
        self_id=self_id,
        names=dict(blackboard.get("agent_names") or {}),
        limits=limits,
    )

    return (
        f"Team goal: {goal}\n"
        f"{criteria_block}{framing_block}\n\n"
        f"Round {current_round}. Latest contributions on the blackboard:\n"
        f"{_format_contributions(peers, self_id=self_id, max_chars=max_peer_chars)}"
        # Run-scoped (§22.5): without this an agent is shown critiques raised during a
        # PREVIOUS run on the same thread — stale feedback about work it is no longer doing.
        f"{_format_critiques(run_critiques(blackboard), self_id=self_id)}\n"
        f"{inbox_block}\n\n"
        "Produce your contribution for this round."
    )
