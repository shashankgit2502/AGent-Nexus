"""Post-consensus artifact producer (ARTIFACTS.md §2A — the designated producer).

§2A is the core behavioural rule: the team **debates → converges → (HITL) →
synthesizes**, and only *then*, if the task calls for one, produces the downloadable
file **from the agreed result**. This is that production step: a single designated
producer agent — built from the real :func:`langchain.agents.create_agent` primitive
(R2) with **only** the artifact tools (§5) — runs one turn over the consensus result
and emits 0..N files via those tools (the "if required is a real decision" rule, §2A
rule 4: prose-only tasks yield no file).

It is invoked as a sub-step of the **synthesizer node** (the control graph stays
``… → Synthesizer → End``, §2A "no new machinery"), persists through the run's
:class:`~app.artifacts.service.ArtifactService`, and returns the artifacts'
``tool_result`` events for the node to stream — after the ``synthesis`` event, before
``run_finished``. A producer failure never collapses the run: the prose answer still
stands; the failure is logged and whatever files were produced are kept (§16 — file
generation must not block/break the run).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

from app.artifacts.descriptor import ArtifactSink
from app.artifacts.service import ArtifactService
from app.tools.artifacts_media import assemble_producer_tools

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are the deliverable PRODUCER for a multi-agent team. The team has already "
    "debated and agreed on a final result; your only job is to turn that agreed result "
    "into the downloadable file(s) the user's task calls for, using your tools.\n\n"
    "Rules:\n"
    "1. Produce a file ONLY if the task clearly calls for a downloadable deliverable "
    "(e.g. 'write a script', 'build the model', 'generate the config'). If the task only "
    "wants a prose answer, produce NO files and reply with a single word: NONE.\n"
    "2. Build each file's content from the AGREED RESULT — do not invent new conclusions.\n"
    "3. Choose correct filenames/extensions. You may produce multiple files.\n"
    "4. Do not restate the prose answer; only call tools to create files (or reply NONE)."
)


def _render_message(goal: str, success_criteria: Sequence[str], final_output: str) -> str:
    """Render the producer's single instruction over the agreed result (§2A source)."""
    criteria = "\n".join(f"- {c}" for c in success_criteria) or "- (none specified)"
    return (
        f"GOAL / TASK:\n{goal}\n\n"
        f"SUCCESS CRITERIA:\n{criteria}\n\n"
        f"THE TEAM'S AGREED RESULT (your single source of truth):\n{final_output}\n\n"
        "Now produce the downloadable file(s) this task requires, or reply NONE."
    )


class ArtifactAgentProducer:
    """A designated producer agent that emits file artifacts post-consensus (§2A).

    Holds the producer's (tool-capable) model and the run-scoped persistence inputs.
    :meth:`produce` builds a fresh sink + tools + agent per call (no shared mutable
    state across runs) and returns the produced artifacts' ``tool_result`` events.
    """

    def __init__(
        self,
        *,
        model: BaseChatModel,
        service: ArtifactService,
        run_id: UUID,
        producer_agent_id: UUID | None,
        doc_chart: bool = True,
        image_gen: bool = False,
    ) -> None:
        self._model = model
        self._service = service
        self._run_id = run_id
        self._producer_agent_id = producer_agent_id
        # Which deliverable tools the producer agent is granted (§13 capability gate).
        self._doc_chart = doc_chart
        self._image_gen = image_gen

    async def produce(
        self,
        *,
        goal: str,
        success_criteria: Sequence[str],
        final_output: str,
        ranked: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        """Run the producer over the agreed result; return its ``tool_result`` events.

        ``ranked`` is the consensus-ranked contributions (§2A implementation note —
        the file reflects what the team agreed, not one agent's draft); ``final_output``
        is the synthesized result the producer builds the file from. Best-effort: a
        producer failure is logged and any already-produced files are returned (§16).
        """
        sink = ArtifactSink(
            service=self._service,
            run_id=self._run_id,
            producer_agent_id=self._producer_agent_id,
        )
        agent = create_agent(
            model=self._model,
            tools=assemble_producer_tools(
                sink, doc_chart=self._doc_chart, image_gen=self._image_gen
            ),
            system_prompt=_SYSTEM_PROMPT,
        )
        message = _render_message(goal, success_criteria, final_output)
        try:
            await agent.ainvoke({"messages": [HumanMessage(content=message)]})
        except Exception:  # noqa: BLE001 — file production must never break the run (§16).
            logger.exception(
                "artifact producer failed for run %s (kept %d produced file(s))",
                self._run_id,
                len(sink.refs),
            )
        if sink.refs:
            logger.info(
                "artifact producer emitted %d file(s) for run %s", len(sink.refs), self._run_id
            )
        return sink.events
