"""Post-run memory consolidation — the write trigger (ARCH §10.2 / §25.3, Item 3 M2).

The Item 3 RCA: a memory-enabled agent's ``/memories/`` store is mounted (so memory
is *loaded* into its prompt) but nothing ever *writes* it — the turn exits via the
``ContributionOut`` tool and never calls ``edit_file``. This module is the approved
fix: a **deterministic post-run consolidation** (ARCH §25.3 "background
consolidation") that, after a run completes, distils each memory-enabled agent's
contributions into one durable **episodic** record (§25.2, "past run findings") via
the cheap non-tool model — no reliance on the model spontaneously choosing to
persist.

Two writes per consolidated agent, both through the same store the agent reads:

1. a structured :class:`~app.memory.items.MemoryItem` (``kind="experience"``) — the
   Memory Explorer's source of truth (§14);
2. a refreshed ``/memories/AGENTS.md`` **rollup** rendered from that agent's records,
   so deepagents' ``MemoryMiddleware`` loads it into the *next* session's prompt —
   closing the recall loop (§10.1).

Resilience (R3, architected not swallowed): a consolidation failure must not fail an
already-finished run. The graph node logs the error with context and continues; the
run's output is already synthesised. The model is given an explicit ``NONE`` escape
so it can decline to record run-specific chatter.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.config import AgentConfig
from app.memory.items import MemoryItem, MemoryItemStore
from app.memory.service import MemoryService

logger = logging.getLogger(__name__)

_NONE = "NONE"

_SYSTEM_PROMPT = (
    "You are the long-term memory consolidator for an AI agent named '{name}'. A "
    "collaboration run just finished. From this agent's own contributions, write a "
    "SHORT durable note (1-3 sentences, first person, e.g. 'I found ...') capturing "
    "only what is worth remembering for FUTURE runs — its key finding, conclusion, "
    "or stance, and how it turned out. Omit run-specific chatter, pleasantries, and "
    "anything not reusable later. Never record secrets or credentials. If nothing is "
    f"worth remembering, reply with exactly '{_NONE}'. Return only the note."
)


def render_consolidation_messages(
    *, agent_name: str, goal: str, contributions: Sequence[Mapping[str, Any]]
) -> list[SystemMessage | HumanMessage]:
    """Build the consolidation prompt (pure; unit-testable on its own)."""
    body = "\n\n".join(
        f"- (round {c.get('round', '?')}, confidence {float(c.get('confidence', 0.0)):.2f}) "
        f"{c.get('content', '')}"
        for c in contributions
    )
    human = (
        f"# Goal\n{goal}\n\n"
        f"# Your contributions this run\n{body}\n\n"
        f"Write the durable note now, or exactly '{_NONE}' if there is nothing to keep."
    )
    return [
        SystemMessage(content=_SYSTEM_PROMPT.format(name=agent_name)),
        HumanMessage(content=human),
    ]


def render_recall_markdown(items: Sequence[MemoryItem]) -> str:
    """Render an agent's records into the ``/memories/AGENTS.md`` recall rollup.

    deepagents loads this whole file into the next session's system prompt (§10.1),
    so it is kept compact: pinned records first (they are the durable preferences),
    then the rest newest-first as :meth:`MemoryItemStore.list_items` already orders
    them. HTML/structure is intentionally minimal — it is reference material for the
    model, not a UI surface (the Explorer reads the structured records instead).
    """
    if not items:
        return "# Long-term memory\n\n(no memories yet)"
    pinned = [i for i in items if i.pinned]
    rest = [i for i in items if not i.pinned]
    lines = ["# Long-term memory", ""]
    if pinned:
        lines.append("## Pinned")
        lines.extend(f"- [{i.kind}] {i.content}" for i in pinned)
        lines.append("")
    lines.append("## Recent")
    lines.extend(f"- [{i.kind}] {i.content}" for i in rest)
    return "\n".join(lines)


@dataclass(frozen=True)
class MemoryConsolidator:
    """Distil a finished run's contributions into each memory agent's long-term memory.

    Args:
        configs: the run's agent configs (only ``memory_enabled`` ones are written).
        items: the structured-record store (§14 source of truth).
        service: the recall-file writer (refreshes ``/memories/AGENTS.md``).
        model: the cheap non-tool model (``require_tools=False``), shared with the
            synthesizer at the composition root (ARCH §9.3 / §4.6).
    """

    configs: Sequence[AgentConfig]
    items: MemoryItemStore
    service: MemoryService
    model: BaseChatModel

    def consolidate_run(self, state: Mapping[str, Any]) -> list[MemoryItem]:
        """Write one episodic record per memory-enabled agent that did real work.

        Returns the records written (for observability/tests); the graph node
        ignores the return. Agents that did not participate, are not memory-enabled,
        contributed nothing usable, or whose summary is ``NONE`` are skipped.
        """
        goal = str(state.get("goal", ""))
        active = {str(a) for a in state.get("active_agent_ids", [])}
        contributions = list(state.get("contributions", []))
        written: list[MemoryItem] = []
        for cfg in self.configs:
            if not cfg.memory_enabled or str(cfg.id) not in active:
                continue
            agent_contribs = _usable_contributions(contributions, agent_id=str(cfg.id))
            if not agent_contribs:
                continue
            note = self._summarize(cfg, goal, agent_contribs)
            if note is None:
                continue
            item = self.items.write_item(
                org_id=cfg.org_id,
                team_id=cfg.team_id,
                agent_id=cfg.id,
                kind="experience",
                content=note,
            )
            self._refresh_rollup(cfg.org_id, cfg.team_id, cfg.id)
            written.append(item)
        return written

    def _summarize(
        self, cfg: AgentConfig, goal: str, contribs: Sequence[Mapping[str, Any]]
    ) -> str | None:
        """Return the durable note for one agent, or ``None`` to skip (incl. ``NONE``)."""
        messages = render_consolidation_messages(
            agent_name=cfg.name, goal=goal, contributions=contribs
        )
        note = self.model.invoke(messages).text.strip()  # langchain-core: .text is a property
        if not note or note.upper() == _NONE:
            return None
        return note

    def _refresh_rollup(self, org_id: UUID, team_id: UUID, agent_id: UUID) -> None:
        """Regenerate ``/memories/AGENTS.md`` from the agent's records (recall, §10.1)."""
        items = self.items.list_items(org_id=org_id, team_id=team_id, agent_id=agent_id)
        markdown = render_recall_markdown(items)
        self.service.upsert(
            org_id=org_id, team_id=team_id, agent_id=agent_id, content=markdown
        )


def _usable_contributions(
    contributions: Sequence[Mapping[str, Any]], *, agent_id: str
) -> list[Mapping[str, Any]]:
    """This agent's real proposals — non-empty content with confidence > 0.

    Filters out the §21.5 confidence-0 abstention markers (a failed/timed-out agent),
    which carry no durable learning, so consolidation never records "[abstained] ..."
    nor wastes a model call on an agent that contributed nothing.
    """
    return [
        c
        for c in contributions
        if c.get("agent_id") == agent_id
        and str(c.get("content", "")).strip()
        and float(c.get("confidence", 0.0)) > 0.0
    ]
