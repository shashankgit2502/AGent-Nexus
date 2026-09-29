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

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Mirrors ``Critique.severity`` on the blackboard (CollabState, ARCH §6).
Severity = Literal["minor", "major", "blocking"]

# Model-facing ``MessageOut.body`` → wire-envelope payload key (ARCH §23.3). Each intent
# names its body differently on the wire, so the mapping is declared once here rather than
# re-derived at every call site. ``VOTE`` is absent deliberately: a vote is a ballot, not a
# statement — its payload is the target and an optional weight, with no body.
_BODY_KEY_BY_INTENT: dict[str, str] = {
    "INFORM": "content",
    "REQUEST": "question",
    "PROPOSE": "content",
    "CRITIQUE": "content",
    "DELEGATE": "subtask",
    "ENDORSE": "reason",
}

# Intents whose recipient is carried in the payload as ``target_agent`` (§23.3 addressing
# note), so the address and the value consensus scores (§8.1) are the same string.
_TARGETED_INTENTS: frozenset[str] = frozenset({"CRITIQUE", "ENDORSE", "VOTE"})


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


#: The seven A2A performatives (ARCH §23.3). Exposed to the model as a closed vocabulary so
#: it selects an intent rather than inventing one — an unknown intent is dropped at
#: validation, which would silently lose the message.
MessageIntent = Literal[
    "INFORM", "REQUEST", "PROPOSE", "CRITIQUE", "DELEGATE", "ENDORSE", "VOTE"
]


class MessageOut(BaseModel):
    """One typed message this agent is sending to a peer (ARCH §23.3).

    This is the **carrier** for the A2A contract (§23.4): messages ride the agent's
    structured turn output rather than separate tool round-trips, so peer communication
    costs no extra model calls — which matters directly, because every additional call is
    another chance to hit a rate limit and abstain (§21.5).

    The shape is deliberately flatter than the wire envelope (:class:`A2AMessage`): the
    model supplies intent, audience, and body; the runtime supplies identity, provenance,
    and validation. A model must never be able to set its own ``sender``.
    """

    model_config = ConfigDict(frozen=True)

    intent: MessageIntent = Field(
        description=(
            "INFORM = share a finding peers can cite | REQUEST = ask a peer for something "
            "you need | PROPOSE = put forward one piece of the solution | DELEGATE = hand "
            "a subtask to a peer | ENDORSE = back a peer's work | VOTE = pick the best "
            "peer contribution | CRITIQUE = challenge a peer's reasoning"
        )
    )
    to: str = Field(
        default="*",
        description=(
            "agent_id of the peer this is for, or '*' to broadcast to the whole team. "
            "REQUEST/DELEGATE/ENDORSE/VOTE/CRITIQUE MUST name a specific peer; "
            "INFORM/PROPOSE are usually broadcast."
        ),
    )
    body: str = Field(
        default="",
        description=(
            "the substance: the finding (INFORM), the question you need answered "
            "(REQUEST), the proposal (PROPOSE), the work you are handing over "
            "(DELEGATE), the reason you agree (ENDORSE), or the problem you found "
            "(CRITIQUE). Be concrete and self-contained — the peer sees this and not "
            "your reasoning. Leave empty for VOTE."
        ),
    )
    severity: Severity = Field(
        default="minor", description="CRITIQUE only: minor | major | blocking"
    )
    source_urls: list[str] = Field(
        default_factory=list,
        description=(
            "INFORM only: the URLs backing this finding, so peers can cite your source "
            "instead of re-researching it"
        ),
    )
    in_reply_to: str | None = Field(
        default=None,
        description="optional msg id from your inbox that this message answers",
    )

    def to_proposed(self) -> dict[str, Any]:
        """Project this into the carrier-agnostic dict :func:`normalize_messages` validates.

        Two things happen here and nowhere else:

        * the flat ``body`` is written to the payload key this intent uses on the wire
          (``question`` for REQUEST, ``subtask`` for DELEGATE, …), so the envelope stays
          §23.3-shaped while the model fills in one simple field;
        * a targeted intent's ``to`` becomes ``payload["target_agent"]``, which is what
          §8.1 scoring reads — the address and the scored value are the same string by
          construction, so they cannot drift.

        Nothing here validates. Everything returned is still untrusted and passes through
        ``normalize_messages`` (roster checks, self-target, budget, dedup) before it is
        allowed onto the blackboard.
        """
        payload: dict[str, Any] = {}
        body = self.body.strip()
        body_key = _BODY_KEY_BY_INTENT.get(self.intent)
        if body_key and body:
            payload[body_key] = body
        if self.intent in _TARGETED_INTENTS:
            payload["target_agent"] = self.to.strip()
        if self.intent == "CRITIQUE":
            payload["severity"] = self.severity
            # A CRITIQUE with no body is not a critique; keep the key present so the
            # required-field check rejects it loudly instead of storing an empty challenge.
            payload.setdefault("content", body)
        if self.intent == "INFORM" and self.source_urls:
            payload["source_urls"] = [u for u in (s.strip() for s in self.source_urls) if u]
        return {
            "intent": self.intent,
            "recipients": self.to.strip() or "*",
            "payload": payload,
            "in_reply_to": self.in_reply_to,
        }


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
    messages: list[MessageOut] = Field(
        default_factory=list,
        description=(
            "typed messages to your peers this round: ask for what you need (REQUEST), "
            "share findings they can cite (INFORM), hand over work you found but do not "
            "own (DELEGATE), back the best peer answer (ENDORSE/VOTE). Leave empty if you "
            "have nothing to say to anyone."
        ),
    )
