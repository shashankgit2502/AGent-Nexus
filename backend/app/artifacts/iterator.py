"""Artifact iteration — revise a file's content per an instruction (ARTIFACTS §10).

Iterate is the Canvas "edit/refine" action: given the artifact's current content and
a natural-language instruction ("make the chart blue", "add error handling"), produce
the **complete revised content**, persisted as a new version (§9). Unlike the original
producer (§2A) — which decides *whether* and *what kind* of file via tools — iterate is
a focused single-model **content transform**: it already knows the target file, so it
asks the model for the full revised content directly (no tool loop), which is the
honest shape for our non-incremental generation (no faked token deltas).

Streaming note (deviation from §10's ``state_delta`` flavour, flagged R4/R6): our
producer emits **complete** files, so there are no genuine incremental deltas to
stream — a fabricated delta stream would be decorative fiction (forbidden). Iterate is
therefore synchronous and returns the full new version; ``state_delta`` (§11.2) stays
the designed seam for a future *token-level* generation path, registered when actually
emitted.
"""

from __future__ import annotations

import logging
from uuid import UUID

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.snapshot import build_org_resolver
from app.core.config import Settings
from app.db.models import Agent as AgentRow
from app.models_layer.resolver import AgentModelRef

logger = logging.getLogger(__name__)

# Text/code kinds that can be revised in v1 (binary office/media iterate is later).
ITERABLE_KINDS: frozenset[str] = frozenset({"code", "markdown", "json", "csv"})

_SYSTEM_PROMPT = (
    "You revise a single file in place. You are given its current content and a "
    "revision instruction. Return ONLY the COMPLETE revised file content — the whole "
    "file, not a diff — with no commentary, no explanation, and no surrounding Markdown "
    "code fences. Preserve the file's format and anything the instruction does not ask "
    "you to change."
)


async def resolve_iterate_model(
    db: AsyncSession,
    *,
    org_id: UUID,
    producer_agent_id: UUID | None,
    settings: Settings,
) -> BaseChatModel | None:
    """Resolve the model used to iterate an artifact — its producer agent's (§10).

    Reuses the producer agent's configured model (the same one that built the file),
    resolved through the org's Model Resolution Layer with the tool gate **relaxed**
    (iterate is a text transform, not tool-calling). Returns ``None`` when the artifact
    has no producer agent (synthesizer-produced) or the agent/model can't resolve — the
    caller turns that into an honest 400 (iterate unsupported for this artifact).
    """
    if producer_agent_id is None:
        return None
    agent = await db.get(AgentRow, producer_agent_id)
    if agent is None or agent.profile_id is None:
        return None
    try:
        resolver = await build_org_resolver(db, org_id=org_id, settings=settings)
        return resolver.resolve(
            AgentModelRef(profile_id=agent.profile_id, override_model_id=agent.override_model_id),
            require_tools=False,
        )
    except Exception:  # noqa: BLE001 — unresolvable model → caller returns 400, logged not swallowed.
        logger.warning(
            "iterate: could not resolve a model for producer agent %s", producer_agent_id,
            exc_info=True,
        )
        return None


def _message_text(message: BaseMessage) -> str:
    """Extract plain text from a model message (string or content-block list)."""
    content = message.content
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts)


def _strip_code_fences(text: str) -> str:
    """Drop a wrapping ``` … ``` fence if the model added one despite instructions."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text.strip("\n")
    lines = stripped.splitlines()
    # Drop the opening fence line (``` or ```lang) and a closing fence line if present.
    body = lines[1:]
    if body and body[-1].strip().startswith("```"):
        body = body[:-1]
    return "\n".join(body).strip("\n")


async def iterate_artifact_content(
    *,
    model: BaseChatModel,
    kind: str,
    filename: str | None,
    current_content: str,
    instruction: str,
) -> str:
    """Return the complete revised file content for ``instruction`` (§10).

    A single model call (no tool loop): the model sees the current content + the
    instruction and returns the full revised file, fence-stripped. Raises if the model
    yields no usable text (a real contract violation, surfaced not swallowed — R3).
    """
    name = filename or f"artifact.{kind}"
    user = (
        f"Current `{kind}` file `{name}`:\n\n{current_content}\n\n"
        f"Revision instruction:\n{instruction}\n\n"
        "Return the full revised file content now."
    )
    messages: list[BaseMessage] = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user),
    ]
    response = await model.ainvoke(messages)
    revised = _strip_code_fences(_message_text(response))
    if not revised.strip():
        raise RuntimeError("iterate model returned empty content")
    return revised
