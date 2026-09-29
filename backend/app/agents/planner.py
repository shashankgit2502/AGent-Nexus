"""The Orchestrator's planner — goal + roster → a :class:`RunPlan` (ARCH §4.1).

This is the "prompt-engineer" half of the locked Orchestrator role (CLAUDE.md §3)
that was never built: one cheap-model call, made **once before any agent runs**,
deciding how this specific goal maps onto this specific team. After it returns, the
orchestrator is passive — there is no master, only a well-informed starting point.

Why a central decision is the right call *here* (R4, and the usual objection)
-----------------------------------------------------------------------------
The standard argument against central assignment is that a router cannot model its
agents' expertise under partial observability. That premise does not hold in this
system: expertise is **declared configuration**, not inferred. Every agent row
carries a name, a description, a persona (``instructions``) and five explicit
capability booleans, so the planner reads the roster rather than guessing at it.
The alternative — agents bidding for work — would cost one extra LLM call per agent
before any work started (ruinous under the ``AGENT_MAX_REQUESTS_PER_MINUTE`` pacer)
and would need an arbiter to settle double-claims, which *would* be the runtime
controller §3 forbids.

The assignment is a **suggestion posted to the blackboard**, not a command: agents
read their framing and remain free to deviate, critique, and cover gaps.

Model choice (locked): the cheap non-tool model, shared with the synthesizer
(``require_tools=False``) — planning is a single structured-output call, not a
ReAct loop.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.config import AgentConfig
from app.agents.plan import PlanOut, RunPlan, fallback_plan, normalize_plan

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are the planning step of a decentralized multi-agent team.

You run ONCE, before any agent starts. You do not supervise execution: you decide how \
this goal maps onto THIS team, and then the agents work as autonomous peers over a \
shared blackboard. Your plan is a strong suggestion, not a command.

Pick the strategy that actually fits the goal — this is the most important decision:

- "decompose": the goal has genuinely distinct parts that different specialists should \
own (e.g. research + financial analysis + compliance review + report writing; or schema \
+ endpoints + auth + tests). Give each agent a DIFFERENT piece.
- "debate": the goal is one judgement call where independent opinions genuinely help \
(e.g. "should we acquire X?", "which architecture is better?"). Emit NO subtasks — the \
team answers the same question in parallel and the best-reasoned answer wins the vote.
- "single_owner": the goal is narrow and splitting it would just create duplicate work \
(e.g. "summarise this document", "fix this one function"). Give ONE agent the task; the \
others automatically become reviewers.

Rules:
1. Assign work ONLY to agent_ids that appear in the roster, copied exactly.
2. Never invent agents and never assume more agents than the roster has. If there are \
more pieces of work than agents, give an agent several subtasks.
3. Match work to the agent's stated role, persona and capabilities. If a piece of work \
needs a capability (rag / web_search / code_interpreter / doc_chart / image_gen), list \
it in "needs" and prefer an agent that has it.
4. round_hint sequences the work in PHASES: round 1 is independent groundwork, later \
rounds build on what peers produced earlier. Never exceed the round budget you are \
given. If the budget is 1, everything is round 1.
5. depends_on records which subtask's output another builds on. It is context for the \
agent, not a scheduler — work is never blocked.
6. acceptance is 1-3 concrete, checkable statements of what "done" means for that \
subtask. Avoid vague criteria.
7. Choose the deliverable honestly. If the user asked for a document, spreadsheet, \
deck, code, or chart, set that kind and a sensible filename. If they only want an \
answer, use "none". Available kinds: none, markdown, code, json, csv, docx, xlsx, \
pptx, pdf, chart, image, archive. Use "archive" when several files are needed.
8. Instructions are written TO the assigned agent, second person, self-contained, and \
specific enough to act on without seeing this prompt.

Be decisive and concrete. A plan of 2-5 well-scoped subtasks beats 10 vague ones."""


def _describe_agent(cfg: AgentConfig) -> str:
    """One roster line: id, name, role, and real capabilities the planner can rely on."""
    capabilities = ", ".join(cfg.capabilities.enabled()) or "no special tools"
    role = (cfg.description or "").strip()
    persona = " ".join((cfg.instructions or "").split())
    if len(persona) > 320:  # bound the roster block; personas can be essays
        persona = persona[:320].rstrip() + "…"
    lines = [f"- agent_id: {cfg.id}", f"  name: {cfg.name}"]
    if role:
        lines.append(f"  role: {role}")
    if persona:
        lines.append(f"  persona: {persona}")
    lines.append(f"  capabilities: {capabilities}")
    lines.append(f"  long-term memory: {'yes' if cfg.memory_enabled else 'no'}")
    return "\n".join(lines)


def render_planning_messages(
    *,
    goal: str,
    success_criteria: Sequence[str],
    configs: Sequence[AgentConfig],
    max_rounds: int,
    team_context: str | None = None,
) -> list[SystemMessage | HumanMessage]:
    """Build the planning prompt (pure — unit-inspectable without a model)."""
    roster = "\n".join(_describe_agent(cfg) for cfg in configs)
    criteria = "\n".join(f"- {c}" for c in success_criteria) or "- (none specified)"
    context_block = f"\n\nTEAM CONTEXT\n{team_context.strip()}" if team_context else ""
    budget = (
        "single round — everything must be round 1"
        if max_rounds == 1
        else f"phases 1..{max_rounds}"
    )
    human = (
        f"GOAL\n{goal}\n\n"
        f"SUCCESS CRITERIA\n{criteria}"
        f"{context_block}\n\n"
        f"ROSTER ({len(configs)} agents — assign only to these ids)\n{roster}\n\n"
        f"ROUND BUDGET: {max_rounds} ({budget})\n\n"
        "Produce the plan."
    )
    return [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=human)]


class LLMPlanner:
    """Plans a run with one structured-output call on the cheap model.

    Satisfies :class:`~app.graph.context.Planner`. Holds the roster configs (loaded
    once at the composition root) so the planner can read declared personas and
    capabilities without any DB access inside the graph.

    Failure policy (R3, matching the rest of the composition root): planning is a
    *quality* step, never a availability risk. Any failure — model error, malformed
    output, provider 429 — degrades to :func:`~app.agents.plan.fallback_plan` (an
    honest ``debate`` plan) and is logged with the cause. A run must never die because
    it could not be planned.
    """

    def __init__(
        self,
        *,
        model: BaseChatModel,
        configs: Sequence[AgentConfig],
        team_context: str | None = None,
    ) -> None:
        self._model = model
        self._configs = list(configs)
        self._team_context = team_context
        self._structured = model.with_structured_output(PlanOut)

    def _roster_ids(self) -> list[str]:
        return [str(c.id) for c in self._configs]

    def _finish(self, raw: object, goal: str, max_rounds: int) -> RunPlan:
        """Validate a planner result against the real roster, or fall back."""
        if not isinstance(raw, PlanOut):
            logger.warning(
                "planner returned %s, not a PlanOut; falling back to an unplanned debate",
                type(raw).__name__,
            )
            return fallback_plan(goal, self._roster_ids())
        plan = normalize_plan(
            raw, roster=self._roster_ids(), configs=self._configs, max_rounds=max_rounds
        )
        logger.info(
            "planned run: strategy=%s subtasks=%d deliverable=%s warnings=%d",
            plan.strategy,
            len(plan.subtasks),
            plan.deliverable.kind,
            len(plan.warnings),
        )
        return plan

    def plan(self, *, goal: str, success_criteria: Sequence[str], max_rounds: int) -> RunPlan:
        """Plan synchronously (the ``invoke`` graph path)."""
        messages = render_planning_messages(
            goal=goal,
            success_criteria=success_criteria,
            configs=self._configs,
            max_rounds=max_rounds,
            team_context=self._team_context,
        )
        try:
            raw = self._structured.invoke(messages)
        except Exception:  # noqa: BLE001 — planning must never fail the run (see class docstring).
            logger.exception("planning failed; falling back to an unplanned debate")
            return fallback_plan(goal, self._roster_ids())
        return self._finish(raw, goal, max_rounds)

    async def aplan(
        self, *, goal: str, success_criteria: Sequence[str], max_rounds: int
    ) -> RunPlan:
        """Plan asynchronously (the real ``astream`` run path)."""
        messages = render_planning_messages(
            goal=goal,
            success_criteria=success_criteria,
            configs=self._configs,
            max_rounds=max_rounds,
            team_context=self._team_context,
        )
        try:
            raw = await self._structured.ainvoke(messages)
        except Exception:  # noqa: BLE001 — planning must never fail the run.
            logger.exception("planning failed; falling back to an unplanned debate")
            return fallback_plan(goal, self._roster_ids())
        return self._finish(raw, goal, max_rounds)
