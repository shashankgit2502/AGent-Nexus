"""Acceptance verification — did the team actually finish the work? (ARCH §4.1)

The gap this closes
-------------------
The planner has always produced ``SubTask.acceptance`` — concrete checks that define
"done" — and :mod:`app.agents.framing` renders them into each agent's brief as
"Done when: …". Nothing then **evaluated** them. A run terminated when the round counter
expired or τ was met, never because the assigned work was verified complete. So a run
could report success with half its subtasks unaddressed, and the human at the gate had no
way to tell without reading every contribution.

This module is the missing acceptance function: one cheap-model call over the plan's
criteria and the consensus-ranked result, producing a per-criterion ✓/✗ with the evidence
that justified it.

What it is not
--------------
It is **not** a gate that blocks the run. Unmet criteria are surfaced at the HITL gate for
the human to weigh (the locked §4.5 decision point), not used to auto-loop or auto-fail.
Two reasons: a verifier is itself a language model and can be wrong, so letting it silently
extend or kill a run would hand a fallible judge unreviewable authority; and the human gate
already exists for exactly this judgement. The report makes the human's decision *informed*
rather than making it for them.

Honest failure mode (R3): a verifier that errors or is absent yields **no report**, not a
fabricated pass. An unverified run must never look like a verified one.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from app.agents.plan import RunPlan

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are the acceptance verifier for a multi-agent team. The team has finished its "
    "work and agreed on a result. Your ONLY job is to check, criterion by criterion, "
    "whether that result actually satisfies what the plan said 'done' would look like.\n\n"
    "Rules:\n"
    "1. Judge ONLY against the agreed result you are shown. Do not assume work happened "
    "off-screen, and do not give credit for intentions or plans to do something.\n"
    "2. For each criterion answer met=true ONLY if the result contains concrete evidence "
    "for it. If it is partially addressed, that is met=false.\n"
    "3. Quote the specific evidence you relied on (a short excerpt) — if you cannot quote "
    "anything, the criterion is not met.\n"
    "4. Be strict but fair. You are the last check before a human reviews this."
)

# How much of the agreed result the verifier is shown. It reads the *whole* result rather
# than one contribution, so a criterion satisfied by any part of the team's output is
# credited; bounded so a long report cannot blow the verifier's context window.
_EVIDENCE_MAX_CHARS = 12000


class AcceptanceCheckOut(BaseModel):
    """One criterion's verdict, as returned by the verifier model."""

    subtask_id: str = Field(description="the subtask id this criterion came from")
    criterion: str = Field(description="the acceptance criterion being judged, verbatim")
    met: bool = Field(description="true ONLY if the agreed result contains evidence for it")
    evidence: str | None = Field(
        default=None, description="short excerpt from the result supporting the verdict"
    )


class AcceptanceReportOut(BaseModel):
    """The verifier model's structured output."""

    checks: list[AcceptanceCheckOut] = Field(default_factory=list)


class AcceptanceCheck(BaseModel):
    """A validated verdict on one criterion (what lands on the blackboard)."""

    model_config = ConfigDict(frozen=True)

    subtask_id: str
    criterion: str
    met: bool
    evidence: str | None = None


class AcceptanceReport(BaseModel):
    """The run's acceptance outcome — what the human sees as ✓/✗ at the gate."""

    model_config = ConfigDict(frozen=True)

    checks: tuple[AcceptanceCheck, ...] = ()

    @property
    def met_count(self) -> int:
        """How many criteria were satisfied."""
        return sum(1 for check in self.checks if check.met)

    @property
    def total(self) -> int:
        """How many criteria the plan defined."""
        return len(self.checks)

    @property
    def complete(self) -> bool:
        """True when every criterion is met (an empty plan is vacuously complete)."""
        return self.met_count == self.total

    def as_state(self) -> dict[str, Any]:
        """Plain-dict projection for the blackboard channel (checkpointer-safe).

        Same rationale as ``RunPlan.as_state``: the model is the validation boundary, the
        dict is the transport, and the Postgres checkpointer never depends on a Pydantic
        round-trip.
        """
        return {
            "checks": [check.model_dump(mode="json") for check in self.checks],
            "met_count": self.met_count,
            "total": self.total,
        }


def planned_criteria(plan: RunPlan | None) -> list[tuple[str, str]]:
    """Every ``(subtask_id, criterion)`` pair the plan defined, in plan order.

    Returns empty when there is no plan or the plan declared no criteria — a ``debate``
    plan legitimately has no subtasks, so "nothing to verify" is a valid outcome and not a
    degraded one.
    """
    if plan is None:
        return []
    return [
        (task.id, criterion)
        for task in plan.subtasks
        for criterion in task.acceptance
        if criterion.strip()
    ]


def render_acceptance_messages(
    *, goal: str, criteria: Sequence[tuple[str, str]], result: str
) -> list[Any]:
    """Build the verifier prompt (pure; separable from the model call)."""
    criteria_block = "\n".join(
        f"- [{subtask_id}] {criterion}" for subtask_id, criterion in criteria
    )
    evidence = result[:_EVIDENCE_MAX_CHARS]
    if len(result) > _EVIDENCE_MAX_CHARS:
        evidence += "\n[…result truncated for length]"
    return [
        SystemMessage(content=_SYSTEM),
        HumanMessage(
            content=(
                f"# The team's goal\n{goal}\n\n"
                f"# Acceptance criteria to check\n{criteria_block}\n\n"
                f"# The team's agreed result\n{evidence}\n\n"
                "Return one verdict per criterion above, in the same order."
            )
        ),
    ]


def normalize_report(
    raw: AcceptanceReportOut, *, criteria: Sequence[tuple[str, str]]
) -> AcceptanceReport:
    """Align the model's verdicts to the plan's real criteria (R5 — validate at the seam).

    The verifier is an LLM, so its output crosses a trust boundary. Rather than trusting the
    returned list, we walk the **plan's** criteria and look up each one's verdict. Two
    consequences, both deliberate:

    * a criterion the verifier skipped is reported **not met** (with no evidence) rather
      than silently dropped — an unjudged criterion is not a passed one;
    * an invented criterion the plan never declared is discarded.

    So the report always has exactly one row per planned criterion, which is what makes the
    ✓/✗ count at the gate trustworthy.
    """
    verdicts = {(check.subtask_id, check.criterion.strip()): check for check in raw.checks}
    # Fallback index by criterion text alone: models routinely echo the criterion correctly
    # while mangling the subtask id, and dropping an otherwise-valid verdict over an id typo
    # would understate the team's real progress.
    by_text = {check.criterion.strip(): check for check in raw.checks}

    checks: list[AcceptanceCheck] = []
    for subtask_id, criterion in criteria:
        found = verdicts.get((subtask_id, criterion.strip())) or by_text.get(criterion.strip())
        checks.append(
            AcceptanceCheck(
                subtask_id=subtask_id,
                criterion=criterion,
                met=bool(found.met) if found is not None else False,
                evidence=(found.evidence or None) if found is not None else None,
            )
        )
    return AcceptanceReport(checks=tuple(checks))


class LLMVerifier:
    """Verifies the plan's acceptance criteria with one structured-output call.

    Uses the cheap non-tool model shared with the planner and synthesizer
    (``require_tools=False``): this is a single judgement call, not a ReAct loop.
    """

    def __init__(self, model: BaseChatModel) -> None:
        self._structured = model.with_structured_output(AcceptanceReportOut)

    def _finish(self, raw: object, criteria: Sequence[tuple[str, str]]) -> AcceptanceReport:
        """Validate a model result into a report, or an empty one if unusable."""
        if not isinstance(raw, AcceptanceReportOut):
            logger.warning("acceptance verifier returned %s; no report", type(raw).__name__)
            return AcceptanceReport()
        return normalize_report(raw, criteria=criteria)

    def verify(
        self, *, goal: str, plan: RunPlan | None, result: str
    ) -> AcceptanceReport:
        """Synchronous verification (the ``invoke`` path)."""
        criteria = planned_criteria(plan)
        if not criteria or not result.strip():
            return AcceptanceReport()
        messages = render_acceptance_messages(goal=goal, criteria=criteria, result=result)
        try:
            raw = self._structured.invoke(messages)
        except Exception:  # noqa: BLE001 — verification must never fail the run (see module docs).
            logger.exception("acceptance verification failed; run continues unverified")
            return AcceptanceReport()
        return self._finish(raw, criteria)

    async def averify(
        self, *, goal: str, plan: RunPlan | None, result: str
    ) -> AcceptanceReport:
        """Asynchronous verification (the real ``astream`` run path)."""
        criteria = planned_criteria(plan)
        if not criteria or not result.strip():
            return AcceptanceReport()
        messages = render_acceptance_messages(goal=goal, criteria=criteria, result=result)
        try:
            raw = await self._structured.ainvoke(messages)
        except Exception:  # noqa: BLE001 — verification must never fail the run.
            logger.exception("acceptance verification failed; run continues unverified")
            return AcceptanceReport()
        return self._finish(raw, criteria)


def evidence_from_contributions(ranked: Sequence[Mapping[str, Any]]) -> str:
    """Assemble the agreed result the verifier judges against.

    Uses the **consensus-ranked** contributions, best first — the same input the synthesizer
    merges (ARTIFACTS §2A: "the file reflects what the team agreed on"). Verifying against
    the ranked set rather than one winner means a criterion satisfied by any part of the
    team's agreed work is credited, which is how a real division of labour reads.
    """
    return "\n\n".join(
        f"[{c.get('agent_id')}] {c.get('content') or ''}".strip() for c in ranked
    ).strip()
