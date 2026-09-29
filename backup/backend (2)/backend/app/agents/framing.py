"""Render a :class:`RunPlan` into per-agent task framing (ARCH §4.1 → §22.2).

The orchestrator decides the plan; this module turns that decision into the string
each agent actually reads. It fills ``CollabState.agent_task_framing`` — the channel
:func:`app.agents.prompts.render_round_message` already injects as "Your task
framing", so **no prompt-layer change is needed**: the seam existed, it was just
being filled with one identical sentence per agent.

What a good framing must tell an agent (and what the old stub told it: nothing):

* **Its own job** — the subtask instruction, written to it specifically.
* **Its done-test** — the acceptance checks, so "finished" is not a vibe.
* **Its inputs** — which peers' work it builds on, by name, so a round-2 agent knows
  whose contribution to read on the blackboard.
* **Its phase** — which round to do the work in (a hint, never a block: the mesh is a
  parallel fan-out, ARCH §23.4).
* **Team context** — the whole plan in one glance, so a peer mesh with no manager
  still shares one mental model of who is doing what.
* **The target** — the deliverable, so agents write toward the file that will be
  produced from the consensus, instead of the producer guessing at the end.

Every section degrades cleanly: an agent with no subtask gets a real reviewer brief
rather than an empty string, and a plan with no subtasks (``debate``) gets shared
framing. There is no path here that produces the old "you are agent <uuid>" stub.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.agents.plan import RunPlan, SubTask

# Keep the team-context block bounded: it is repeated in every agent's prompt every
# round, so an unbounded roster would multiply into the token budget (the same
# reasoning as AGENT_PEER_CONTENT_MAX_CHARS in config.py).
_MAX_LISTED_SUBTASKS = 12


def _agent_label(agent_id: str, names: Mapping[str, str]) -> str:
    """Human name for an agent id, falling back to a short id (never a raw UUID wall)."""
    name = names.get(agent_id)
    if name:
        return name
    return agent_id if len(agent_id) <= 8 else f"{agent_id[:8]}…"


def _deliverable_line(plan: RunPlan) -> str:
    """One line telling every agent what the team is ultimately building."""
    deliverable = plan.deliverable
    if not deliverable.wanted:
        return (
            "Final deliverable: a written answer only — no file will be produced, so "
            "put the substance in your contribution text."
        )
    parts = [f"Final deliverable: a {deliverable.kind.upper()} file"]
    if deliverable.filename:
        parts.append(f"({deliverable.filename})")
    line = " ".join(parts)
    if deliverable.notes:
        line += f" — {deliverable.notes}"
    return (
        f"{line}\nWrite your contribution so this file can be built directly from the "
        "team's agreed result: be concrete, structured, and include the actual content "
        "(numbers, sections, code) rather than describing what should be written."
    )


def _team_overview(plan: RunPlan, self_id: str, names: Mapping[str, str]) -> str:
    """The shared who-does-what block — the peer mesh's common mental model."""
    if not plan.subtasks:
        return ""
    lines = ["Team plan (you are one peer; there is no manager):"]
    for task in plan.subtasks[:_MAX_LISTED_SUBTASKS]:
        who = (
            "YOU"
            if task.assigned_agent_id == self_id
            else _agent_label(task.assigned_agent_id, names)
        )
        lines.append(f"  [{task.id}] {task.title} → {who} (round {task.round_hint})")
    remaining = len(plan.subtasks) - _MAX_LISTED_SUBTASKS
    if remaining > 0:
        lines.append(f"  … and {remaining} more")
    return "\n".join(lines)


def _dependency_line(task: SubTask, plan: RunPlan, names: Mapping[str, str]) -> str:
    """Name the peers whose output this subtask builds on (context, not scheduling)."""
    if not task.depends_on:
        return ""
    by_id = {t.id: t for t in plan.subtasks}
    parts: list[str] = []
    for dep_id in task.depends_on:
        dep = by_id.get(dep_id)
        if dep is None:
            continue
        parts.append(f"{dep.title} (by {_agent_label(dep.assigned_agent_id, names)})")
    if not parts:
        return ""
    return (
        "Builds on: "
        + "; ".join(parts)
        + ".\nRead those peers' contributions on the blackboard before writing yours; "
        "if their work is not visible yet, state your assumptions and refine next round."
    )


def _own_assignment(tasks: Sequence[SubTask], plan: RunPlan, names: Mapping[str, str]) -> str:
    """The agent's own brief — instruction, done-test, inputs, phase."""
    blocks: list[str] = []
    for task in tasks:
        section = [f"YOUR ASSIGNMENT [{task.id}] {task.title}", task.instruction]
        if task.acceptance:
            section.append("Done when:\n" + "\n".join(f"  - {check}" for check in task.acceptance))
        dependency = _dependency_line(task, plan, names)
        if dependency:
            section.append(dependency)
        section.append(
            f"Work this in round {task.round_hint}. In earlier rounds, prepare or "
            "gather what you need; in later rounds, refine it against peer feedback."
        )
        blocks.append("\n".join(section))
    return "\n\n".join(blocks)


def _reviewer_brief(plan: RunPlan, names: Mapping[str, str]) -> str:
    """Brief for an agent the plan gave no subtask — a real job, not idling.

    A peer with nothing assigned must not simply re-answer the whole goal (that is the
    clone behaviour this whole change exists to remove). Reviewing is genuinely useful
    work and it is what drives the critique edges in the Session Workspace.
    """
    owners = (
        ", ".join(sorted({_agent_label(t.assigned_agent_id, names) for t in plan.subtasks}))
        or "your peers"
    )
    return (
        "YOUR ROLE: reviewer.\n"
        f"The plan assigns the delivery work to {owners}. Do not duplicate their work. "
        "Your job is to make the team's output correct: check their contributions for "
        "errors, gaps, unstated assumptions, and risks; raise targeted critiques; and "
        "contribute the specific corrections or missing pieces you find. If you spot "
        "something nobody is covering, cover it yourself and say so."
    )


def _debate_brief(goal: str) -> str:
    """Brief for a ``debate`` plan — every agent answers the same question, on purpose."""
    return (
        "YOUR ROLE: independent analyst on a shared question.\n"
        f"This task was NOT split up: the team deliberately tackles it in parallel so "
        f"the strongest reasoning wins the confidence-weighted vote. Answer it fully "
        f"and in your own voice — {goal}\n"
        "Do not assume a peer is covering part of it. Where you disagree with a peer, "
        "say so explicitly and explain why."
    )


def render_agent_framing(
    plan: RunPlan,
    *,
    goal: str,
    roster: Sequence[str],
    names: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build ``agent_task_framing`` (agent_id → brief) for the whole roster.

    Every roster agent gets a brief — assigned work, a reviewer role, or the shared
    debate brief — so no agent is ever left with the old identical stub sentence.

    Args:
        plan: the validated plan (its assignees are already guaranteed on-roster).
        goal: the run goal, used by the ``debate`` brief.
        roster: ``active_agent_ids`` — the authoritative set to produce framing for.
        names: optional agent_id → display name, so briefs read "Legal Reviewer"
            instead of a UUID. Missing names degrade to a short id.
    """
    names = names or {}
    overview = _team_overview(plan, self_id="", names=names)
    deliverable = _deliverable_line(plan)

    framing: dict[str, str] = {}
    for agent_id in roster:
        own = plan.for_agent(agent_id)
        if own:
            body = _own_assignment(own, plan, names)
        elif plan.strategy == "debate" or not plan.subtasks:
            body = _debate_brief(goal)
        else:
            body = _reviewer_brief(plan, names)

        # Re-render the overview per agent so "YOU" marks this agent's own rows.
        team_block = _team_overview(plan, self_id=agent_id, names=names) or overview
        sections = [
            f"Team approach: {plan.summary}" if plan.summary else "",
            body,
            team_block,
            deliverable,
        ]
        framing[agent_id] = "\n\n".join(section for section in sections if section)
    return framing
