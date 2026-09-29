"""Knowledge chunk metadata + the tenant/scope retrieval filter (ARCH §10.5).

Two pure functions, kept together because they are two halves of one contract:
:func:`chunk_metadata` decides what every ingested chunk *carries*, and
:func:`build_knowledge_filter` decides what a retrieval is *allowed to see*. They
must agree on the metadata keys, so they live in one place and are unit-tested
against each other.

R1/R3 note — why the filter is NOT the spec's literal shape
-----------------------------------------------------------
ARCH §10.5.2 sketches ``agent_id: {"$in": [None, agent_id]}`` (team-shared OR this
agent's private). Verified against ``langchain_postgres`` 0.0.17, ``$in`` **raises**
``NotImplementedError`` on a ``None`` element — JSONB has no null branch there. The
document carries the standing caveat to re-verify filter syntax at build time.
Root cause: a ``None`` in the metadata value set, not the rule itself. Faithful fix
(verified live against pgvector): never store a null ``agent_id`` — tag team-shared
chunks with ``scope="team"`` and agent-private chunks with ``scope="agent"`` +
``agent_id`` — then express the rule with supported operators:

    {"$and": [{"org_id": ...}, {"team_id": ...},
              {"$or": [{"scope": "team"}, {"agent_id": ...}]}]}

Same intent (team-shared OR own-private), tenant-isolated, no nulls.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal
from uuid import UUID

KnowledgeScope = Literal["team", "agent", "conversation"]

# Bound names of the retriever tools (= the decorated function names in
# :mod:`app.knowledge.retriever`). Defined here, in a leaf module with no
# ``app.agents`` import, so the agent factory can detect a tool's presence without
# importing ``retriever`` (which imports ``app.agents.config``) — avoiding an
# ``app.agents`` ↔ ``app.knowledge.retriever`` import cycle.
KNOWLEDGE_TOOL_NAME = "search_knowledge"  # team/agent RAG (§10.5.2)
CONVERSATION_TOOL_NAME = "search_uploaded_files"  # per-turn chat attachments (§8.5.3)

# Sentinel for "only specified sources" with an empty source list: it can never
# collide with a real (UUID) source_id, so the filter matches nothing — an agent
# restricted to specified sources that has none attached sees no knowledge.
_NO_SOURCE_SENTINEL = "__no_source__"


def chunk_metadata(
    *,
    org_id: UUID,
    source_id: UUID,
    team_id: UUID | None = None,
    agent_id: UUID | None = None,
    conversation_id: UUID | None = None,
) -> dict[str, str]:
    """Build the metadata stamped on every chunk of one knowledge source (§10.5.1).

    Scope precedence (each chunk has exactly one scope, no nulls stored — module note):

    * ``conversation_id`` set → a **transient chat attachment** (``scope="conversation"``,
      ARCH §8.5.3): visible only inside that conversation, never to team
      ``search_knowledge`` (its ``scope`` is neither ``team`` nor ``agent``).
    * ``agent_id`` set → an **agent-private** source (``scope="agent"``).
    * otherwise → **team-shared** (``scope="team"``).

    ``team_id`` is optional: a no-team conversation's attachment has no team, so the
    key is simply omitted (the conversation filter scopes by ``org_id`` +
    ``conversation_id``, not team).
    """
    if conversation_id is not None:
        scope: KnowledgeScope = "conversation"
    elif agent_id is not None:
        scope = "agent"
    else:
        scope = "team"
    metadata: dict[str, str] = {
        "org_id": str(org_id),
        "source_id": str(source_id),
        "scope": scope,
    }
    if team_id is not None:
        metadata["team_id"] = str(team_id)
    if agent_id is not None:
        metadata["agent_id"] = str(agent_id)
    if conversation_id is not None:
        metadata["conversation_id"] = str(conversation_id)
    return metadata


def build_knowledge_filter(
    *,
    org_id: UUID,
    team_id: UUID,
    agent_id: UUID,
    only_specified_sources: bool,
    source_ids: Sequence[UUID],
) -> dict[str, Any]:
    """Build the PGVector metadata filter for one agent's ``search_knowledge`` (§10.5.2).

    The agent may see: its org + team's **team-shared** chunks OR its **own
    agent-private** chunks; never another agent's private chunks and never another
    team/org (tenant isolation). When ``only_specified_sources`` is on, results are
    further restricted to ``source_ids`` (the "Only use specified sources" toggle,
    §10.5.3).
    """
    clauses: list[dict[str, Any]] = [
        {"org_id": str(org_id)},
        {"team_id": str(team_id)},
        {"$or": [{"scope": "team"}, {"agent_id": str(agent_id)}]},
    ]
    if only_specified_sources:
        ids = [str(s) for s in source_ids] or [_NO_SOURCE_SENTINEL]
        clauses.append({"source_id": {"$in": ids}})
    return {"$and": clauses}


def build_conversation_filter(*, org_id: UUID, conversation_id: UUID) -> dict[str, Any]:
    """Build the PGVector filter for a conversation's **transient attachments** (§8.5.3).

    Mirrors :func:`build_knowledge_filter` for the chat-upload case: a turn may see
    only files uploaded to *this* conversation (``scope="conversation"`` chunks tagged
    with this ``conversation_id``), tenant-isolated by ``org_id``. Deliberately does
    **not** match team/agent knowledge — transient attachments are a separate namespace
    that never joins the team KB unless explicitly promoted (§8.5.3).
    """
    return {"$and": [{"org_id": str(org_id)}, {"conversation_id": str(conversation_id)}]}
