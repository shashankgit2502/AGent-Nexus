"""Structured output for one agent turn (ARCHITECTURE.md §22.3).

Each mesh agent must return a *typed* result so the consensus engine (§8) can
score it deterministically rather than parsing free text. We bind this schema via
``create_deep_agent(response_format=ContributionOut)``; LangChain's ToolStrategy
exposes it to the model as a tool named after the class and returns the parsed
instance on the run result's ``structured_response`` key (verified end-to-end
against langchain 1.3.9 / deepagents 0.6.10).

Why Pydantic (not the TypedDict sketched in ARCH §22.3): a Pydantic model gives
us boundary validation (R5) — notably the ``confidence`` ``0.0–1.0`` bound, which
the confidence-weighted vote (§8) relies on. The field shape is otherwise
identical to the spec.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Mirrors ``Critique.severity`` on the blackboard (CollabState, ARCH §6).
Severity = Literal["minor", "major", "blocking"]


class CritiqueOut(BaseModel):
    """A single critique an agent levels at a peer's prior contribution.

    Maps onto a blackboard :class:`~app.graph.state.Critique` once the turn's
    ``from_agent``/``round`` are filled in by the runtime (§22.2 output mapping).
    """

    model_config = ConfigDict(frozen=True)

    target_agent: str = Field(description="agent_id of the peer being critiqued")
    severity: Severity = Field(
        default="minor",
        description="how serious the issue is: minor | major | blocking",
    )
    content: str = Field(description="the substance of the critique")


class ContributionOut(BaseModel):
    """One agent's proposal for the current round (the agent's required output).

    The runtime stamps ``agent_id``/``round`` and surfaces ``tool_calls`` for
    transparency when mapping this to a blackboard ``Contribution`` (§22.2).
    """

    model_config = ConfigDict(frozen=True)

    content: str = Field(description="this agent's proposal/answer for the round")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="0.0–1.0 self-assessed confidence in this contribution",
    )
    responds_to: list[str] = Field(
        default_factory=list,
        description=(
            "agent_ids of the specific peers whose prior-round contributions this "
            "proposal directly builds on or answers (leave empty in the opening "
            "round or if not building on a specific peer)"
        ),
    )
    critiques: list[CritiqueOut] = Field(
        default_factory=list,
        description="optional critiques of peers' prior-round contributions",
    )
