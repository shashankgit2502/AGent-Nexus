"""The run plan — what the team will do and who does what (ARCH §4.1 / §22.2).

This is the structured output of the **Orchestrator entry node**. The locked role
(CLAUDE.md §3) is "prompt-engineer + agent spawner, passive after dispatch": the
orchestrator decides *once*, before any agent runs, how the goal is split across the
roster, then never intervenes again. That single decision is this module's schema.

Why a plan and not just a prompt string
---------------------------------------
Before this, ``agent_task_framing`` was one identical sentence per agent, so every
peer answered the whole goal in isolation and the "team" was a poll of clones. A
plan makes the assignment **explicit, validated, and renderable**: the agents get a
job, the UI gets something to show, and the producer learns the deliverable up front
instead of guessing at the end.

Three honest strategies (the generality fix)
--------------------------------------------
Decomposition is not always correct. Forcing N subtasks onto N agents is what makes
four agents redundantly summarise a one-page document. So the plan carries a
``strategy``:

* ``decompose``    — genuinely multi-faceted work; each agent owns a different piece.
* ``debate``       — a judgement call; every agent tackles the *same* question and the
                     confidence-weighted vote is the point (the prior behaviour, now a
                     deliberate choice rather than the only option).
* ``single_owner`` — narrow work; one agent owns it, the others review.

Not a scheduler (locked-decision boundary)
------------------------------------------
``depends_on`` is recorded for prompt context and the UI dependency view, but it is
**never enforced as blocking**. The mesh is a parallel ``Send()`` fan-out where round
N sees only round N-1 (ARCH §23.4), so ordering is expressed as ``round_hint`` — a
phase — not as a wait. Enforcing a true dependency would require a runtime arbiter,
which is exactly the "orchestrator as controller" that §3 forbids.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agents.config import AgentConfig, Capabilities

# ── Vocabularies ──────────────────────────────────────────────────────────────

PlanStrategy = Literal["decompose", "debate", "single_owner"]

# Every downloadable kind the artifact layer can actually produce, derived from the
# real tool surface so the planner can never promise a file the producer cannot build:
#   text tools  (app/tools/artifacts.py)       → markdown, code, json, csv
#   office/media(app/artifacts/generators.py)  → docx, xlsx, pptx, pdf, chart, image, archive
# ``none`` is a first-class answer: a prose-only task must produce no file (§2A rule 4).
DeliverableKind = Literal[
    "none",
    "markdown",
    "code",
    "json",
    "csv",
    "docx",
    "xlsx",
    "pptx",
    "pdf",
    "chart",
    "image",
    "archive",
]

# Capability keys a subtask may declare it needs; validated against the real
# Capabilities fields so a typo can never silently disable the coverage check.
_VALID_CAPABILITIES: frozenset[str] = frozenset(Capabilities.model_fields)


# ── Model-facing schema (what the planner LLM returns) ────────────────────────


class SubTaskOut(BaseModel):
    """One assigned piece of work, as proposed by the planner model."""

    id: str = Field(description="short stable id, e.g. 't1'")
    title: str = Field(description="a few words naming the piece of work (UI label)")
    instruction: str = Field(
        description=(
            "self-contained instruction for the assigned agent: what to produce, "
            "what inputs to use, what 'good' looks like. Written TO that agent."
        )
    )
    assigned_agent_id: str = Field(description="agent_id from the roster; must be exact")
    round_hint: int = Field(default=1, description="which debate round to do this in (1-based)")
    depends_on: list[str] = Field(
        default_factory=list, description="ids of subtasks whose output this builds on"
    )
    acceptance: list[str] = Field(
        default_factory=list, description="concrete checks that mean this subtask is done"
    )
    needs: list[str] = Field(
        default_factory=list,
        description=(
            "capabilities required: rag, web_search, code_interpreter, doc_chart, image_gen"
        ),
    )


class DeliverableOut(BaseModel):
    """The downloadable output the task calls for (or ``none`` for a prose answer)."""

    kind: DeliverableKind = Field(description="the file type to produce, or 'none'")
    filename: str | None = Field(default=None, description="suggested filename with extension")
    notes: str | None = Field(
        default=None, description="what the file must contain (sections, sheets, slides)"
    )


class PlanOut(BaseModel):
    """The planner model's structured output (validated into a :class:`RunPlan`)."""

    strategy: PlanStrategy = Field(
        description="decompose (split the work) | debate (all tackle the same question) "
        "| single_owner (one does it, others review)"
    )
    summary: str = Field(description="one sentence: how this team will approach the goal")
    subtasks: list[SubTaskOut] = Field(default_factory=list)
    deliverable: DeliverableOut = Field(default_factory=lambda: DeliverableOut(kind="none"))


# ── Validated, run-ready schema (what lands on the blackboard) ────────────────


class SubTask(BaseModel):
    """A validated subtask: the agent is real, the round is in range."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    instruction: str
    assigned_agent_id: str
    round_hint: int = 1
    depends_on: tuple[str, ...] = ()
    acceptance: tuple[str, ...] = ()
    needs: tuple[str, ...] = ()


class Deliverable(BaseModel):
    """The validated downloadable target for the run."""

    model_config = ConfigDict(frozen=True)

    kind: DeliverableKind = "none"
    filename: str | None = None
    notes: str | None = None

    @property
    def wanted(self) -> bool:
        """True when the task actually calls for a file (§2A rule 4)."""
        return self.kind != "none"


class RunPlan(BaseModel):
    """The team's plan for one run — the orchestrator's single decision."""

    model_config = ConfigDict(frozen=True)

    strategy: PlanStrategy
    summary: str
    subtasks: tuple[SubTask, ...] = ()
    deliverable: Deliverable = Deliverable()
    # Honest degradation surface (never silent): unassignable subtasks, clamped
    # rounds, and capability gaps the roster cannot cover.
    warnings: tuple[str, ...] = ()

    def for_agent(self, agent_id: str) -> tuple[SubTask, ...]:
        """Every subtask assigned to ``agent_id`` (an agent may own more than one)."""
        return tuple(t for t in self.subtasks if t.assigned_agent_id == agent_id)

    def as_state(self) -> dict[str, Any]:
        """Plain-dict projection for the blackboard channel (checkpointer-safe).

        ``CollabState`` holds plain structures (TypedDicts / JSON-able values) so the
        Postgres checkpointer never depends on a Pydantic serializer round-trip; the
        model is the validation boundary, the dict is the transport.
        """
        return self.model_dump(mode="json")


def plan_from_state(value: Any) -> RunPlan | None:
    """Rebuild a :class:`RunPlan` from the blackboard channel, or ``None``.

    Tolerant by design: a checkpoint written before the plan channel existed (or by a
    future version with extra keys) must not crash a resumed run — it simply has no
    plan and the readers fall back to unplanned behaviour.
    """
    if not isinstance(value, Mapping):
        return None
    try:
        return RunPlan.model_validate(dict(value))
    except Exception:  # noqa: BLE001 — a malformed/legacy plan degrades to "no plan".
        return None


# ── Validation: planner output → run-ready plan ───────────────────────────────


def normalize_plan(
    raw: PlanOut,
    *,
    roster: Sequence[str],
    configs: Sequence[AgentConfig] = (),
    max_rounds: int = 3,
) -> RunPlan:
    """Validate a planner proposal against the **real** roster and round budget (R5).

    The planner is an LLM, so its output crosses a trust boundary. Four repairs, each
    recorded as a warning rather than applied silently (R3):

    1. **Unknown assignee** → reassigned round-robin across the real roster. A
       hallucinated agent id must never strand a piece of work.
    2. **Out-of-range round** → clamped into ``1..max_rounds``. The lightweight chat
       path runs ``max_rounds=1``, where a 3-phase plan is unexecutable.
    3. **Dangling ``depends_on``** → dropped (it would render a phantom edge).
    4. **Capability gap** → kept, but warned: the subtask needs e.g. ``web_search``
       and no assigned agent has it, so the user learns why the output is thin.

    An empty roster yields an empty plan — there is nobody to assign to.
    """
    if not roster:
        return RunPlan(strategy=raw.strategy, summary=raw.summary, deliverable=Deliverable())

    known = set(roster)
    capability_by_agent = {str(c.id): set(c.capabilities.enabled()) for c in configs}
    warnings: list[str] = []
    subtasks: list[SubTask] = []
    seen_ids: set[str] = set()

    for index, task in enumerate(raw.subtasks):
        assignee = task.assigned_agent_id
        if assignee not in known:
            assignee = roster[index % len(roster)]
            warnings.append(
                f"subtask {task.id!r} named an unknown agent "
                f"{task.assigned_agent_id!r}; reassigned to {assignee}"
            )

        round_hint = max(1, min(int(task.round_hint or 1), max_rounds))
        if round_hint != task.round_hint:
            warnings.append(
                f"subtask {task.id!r} asked for round {task.round_hint}; "
                f"clamped to {round_hint} (max_rounds={max_rounds})"
            )

        # Keep ids unique so depends_on / UI keys stay unambiguous.
        task_id = task.id if task.id and task.id not in seen_ids else f"t{index + 1}"
        seen_ids.add(task_id)

        needs = tuple(n for n in task.needs if n in _VALID_CAPABILITIES)
        missing = sorted(set(needs) - capability_by_agent.get(assignee, set()))
        if missing:
            warnings.append(
                f"subtask {task_id!r} needs {', '.join(missing)} but its agent does not "
                "have that capability enabled — output may be limited"
            )

        subtasks.append(
            SubTask(
                id=task_id,
                title=task.title.strip() or task_id,
                instruction=task.instruction.strip(),
                assigned_agent_id=assignee,
                round_hint=round_hint,
                depends_on=(),  # filled below, once every id is known
                acceptance=tuple(a for a in task.acceptance if a.strip()),
                needs=needs,
            )
        )

    subtasks = _resolve_dependencies(subtasks, raw.subtasks, warnings)

    return RunPlan(
        strategy=raw.strategy,
        summary=raw.summary.strip(),
        subtasks=tuple(subtasks),
        deliverable=Deliverable(
            kind=raw.deliverable.kind,
            filename=(raw.deliverable.filename or None),
            notes=(raw.deliverable.notes or None),
        ),
        warnings=tuple(warnings),
    )


def _resolve_dependencies(
    subtasks: list[SubTask], raw: Sequence[SubTaskOut], warnings: list[str]
) -> list[SubTask]:
    """Keep only ``depends_on`` ids that resolve to a real subtask (and not itself)."""
    valid = {t.id for t in subtasks}
    resolved: list[SubTask] = []
    for task, original in zip(subtasks, raw, strict=False):
        kept = tuple(dep for dep in original.depends_on if dep in valid and dep != task.id)
        dropped = [d for d in original.depends_on if d not in valid]
        if dropped:
            warnings.append(
                f"subtask {task.id!r} depends on unknown subtask(s) "
                f"{', '.join(repr(d) for d in dropped)}; dropped"
            )
        resolved.append(task.model_copy(update={"depends_on": kept}))
    return resolved


#: Prefix for subtask ids created by a peer hand-off, so an amendment is always
#: distinguishable from planner-authored work in the UI and in the plan itself.
DELEGATED_ID_PREFIX = "d-"


def apply_delegations(
    plan: RunPlan | None,
    *,
    messages: Sequence[Mapping[str, Any]],
    roster: Sequence[str],
    max_rounds: int,
    current_round: int,
) -> tuple[RunPlan | None, list[dict[str, Any]]]:
    """Fold this round's ``DELEGATE`` messages into the plan (ARCH §4.1 / §23.3).

    This is the re-planning half of the Orchestrator problem. The plan is decided **once**,
    before any agent has run, from the goal alone — so it cannot know what the work will
    reveal. Every production research system re-plans mid-flight for exactly this reason.
    But re-entering the orchestrator would make it the runtime controller §3 forbids, so
    adaptation happens **peer-to-peer over the blackboard** instead: an agent that finds
    work it does not own hands it to the peer who does, and the plan absorbs that.

    Scope (deliberately narrow — a flagged narrowing of "DELEGATE/PROPOSE"):
    only ``DELEGATE`` amends the plan. It states unambiguously *"this is work, and it is
    yours"*, which maps cleanly onto a new assigned subtask. ``PROPOSE`` is a suggestion —
    it already reaches every peer through the inbox and the contributions, and inventing a
    plan change from it would put words in the team's mouth.

    Idempotent by construction: each amendment's subtask id is derived from the originating
    message id, so re-applying the same message (a replayed round, a resumed checkpoint)
    cannot duplicate the work. Returns ``(plan, amendment_events)``; the plan is returned
    unchanged — and no events emitted — when nothing was delegated.
    """
    if plan is None:
        return None, []

    known = {str(a) for a in roster}
    existing_ids = {task.id for task in plan.subtasks}
    added: list[SubTask] = []
    events: list[dict[str, Any]] = []

    for message in messages:
        if message.get("intent") != "DELEGATE":
            continue
        recipients = message.get("recipients") or []
        if isinstance(recipients, str) or not recipients:
            continue  # broadcast delegations are rejected upstream; ignore defensively
        assignee = str(recipients[0])
        if assignee not in known:
            continue
        task_id = f"{DELEGATED_ID_PREFIX}{message.get('id')}"
        if task_id in existing_ids:
            continue  # already folded in on an earlier pass
        payload = message.get("payload") or {}
        subtask = str(payload.get("subtask") or "").strip()
        if not subtask:
            continue

        existing_ids.add(task_id)
        added.append(
            SubTask(
                id=task_id,
                # Kept short for the UI label; the full instruction carries the detail.
                title=subtask[:60] + ("…" if len(subtask) > 60 else ""),
                instruction=subtask,
                assigned_agent_id=assignee,
                # Delegated work lands in the NEXT round — the recipient only sees the
                # message then (§23.4) — clamped to the run's remaining budget.
                round_hint=max(1, min(current_round + 1, max_rounds)),
                depends_on=(),
                acceptance=(),
                needs=(),
            )
        )
        events.append(
            make_amendment_event(
                round=int(message.get("round") or current_round),
                by_agent=str(message.get("sender") or ""),
                change=f"delegated to {assignee}: {subtask}",
                subtask_id=task_id,
                reason=str(payload.get("rationale") or "") or None,
            )
        )

    if not added:
        return plan, []
    return plan.model_copy(update={"subtasks": (*plan.subtasks, *added)}), events


def make_amendment_event(
    *, round: int, by_agent: str, change: str, subtask_id: str | None, reason: str | None
) -> dict[str, Any]:
    """The ``plan_amended`` AG-UI record (§24.4) — who changed the plan, and to what.

    Provenance is the point: a plan that silently mutates is worse than no plan, because the
    user's mental model of who-is-doing-what goes stale without any signal.
    """
    return {
        "round": round,
        "by_agent": by_agent,
        "change": change,
        "subtask_id": subtask_id,
        "reason": reason,
    }


def fallback_plan(goal: str, roster: Sequence[str]) -> RunPlan:
    """The unplanned plan: every agent debates the whole goal (pre-planner behaviour).

    Used when no planner is wired (foundation tests, a team with no viable model) or
    when planning fails. It is a **real** ``debate`` plan rather than a fake
    decomposition — honest about the fact that no decomposition happened (R3).
    """
    return RunPlan(
        strategy="debate",
        summary=f"No planner available — every agent addresses the goal directly: {goal}",
        subtasks=(),
        deliverable=Deliverable(),
        warnings=("no planner configured; agents were not given individual assignments",),
    )
