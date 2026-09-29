"""``LLMSynthesizer`` — the production final-synthesis merge (ARCHITECTURE.md §4.6).

The Synthesizer is a **plain node, not an agent** (locked, CLAUDE.md §3): it does
not need to call tools, so it runs on a *cheaper non-tool model* and simply merges
the consensus-ranked contributions into one unified answer with a single model
invocation. No ReAct loop, no structured-output tool — just text in, text out.

This class is the composition piece that satisfies the
:class:`~app.graph.context.Synthesizer` Protocol. It is injected into the graph via
``MeshContext(synthesizer=...)`` so the ``synthesizer`` node stays a thin, testable
plain node (same DI seam as :class:`~app.agents.mesh.FactoryMeshRunner` for the
mesh). The model is resolved elsewhere — at the composition root (Step 9) with
``ModelResolver.resolve(ref, require_tools=False)`` (the §9.3 gate is relaxed for
the synthesizer) — and passed in here, keeping this layer free of resolver wiring
and trivially testable with a scripted model.

R1 note: ``AIMessage.text`` is a **property** in langchain-core 1.4.7 (calling
``.text()`` is deprecated) — verified before use.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

_SYSTEM_PROMPT = (
    "You are the final synthesizer for a team of peer AI agents that debated a "
    "goal over several rounds and reached consensus. You are NOT one of the "
    "agents and you do not use tools. Merge the agents' ranked contributions "
    "into a single, coherent, self-contained answer to the goal. Resolve "
    "overlaps, prefer higher-confidence material, and do not invent facts beyond "
    "what the contributions support. Return only the final answer."
)


def _format_ranked(ranked: Sequence[Mapping[str, object]]) -> str:
    """Render the ranked contributions into a numbered, confidence-tagged block."""
    if not ranked:
        return "(no contributions were produced)"
    lines: list[str] = []
    for position, contribution in enumerate(ranked, start=1):
        confidence = contribution.get("confidence", 0.0)
        agent_id = contribution.get("agent_id", "?")
        content = contribution.get("content", "")
        lines.append(f"{position}. [{agent_id}, confidence={confidence:.2f}]\n{content}")
    return "\n\n".join(lines)


def render_synthesis_messages(
    *, goal: str, success_criteria: Sequence[str], ranked: Sequence[Mapping[str, object]]
) -> list[SystemMessage | HumanMessage]:
    """Build the prompt for the synthesis model (pure; unit-testable on its own)."""
    criteria = "\n".join(f"- {c}" for c in success_criteria) or "(none specified)"
    human = (
        f"# Goal\n{goal}\n\n"
        f"# Success criteria\n{criteria}\n\n"
        f"# Ranked contributions (best first)\n{_format_ranked(ranked)}\n\n"
        "Write the unified final answer now."
    )
    return [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=human)]


@dataclass(frozen=True)
class LLMSynthesizer:
    """Merge ranked contributions into one output with a single model call.

    Args:
        model: a resolved chat model (``require_tools=False``; ARCH §9.3). Async
            clients are fine — :meth:`synthesize` is the sync entry the plain
            synthesizer node uses; an async variant can be added when the run loop
            goes fully async (R5) without changing this seam.
    """

    model: BaseChatModel

    def synthesize(
        self, *, goal: str, success_criteria: list[str], ranked: Sequence[Mapping[str, object]]
    ) -> str:
        """Return the unified final answer for the goal."""
        messages = render_synthesis_messages(
            goal=goal, success_criteria=success_criteria, ranked=ranked
        )
        result = self.model.invoke(messages)
        return result.text  # langchain-core 1.4.7: .text is a property (R1-verified)
