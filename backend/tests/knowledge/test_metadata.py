"""Knowledge metadata + tenant filter unit tests (ARCH §10.5.1/§10.5.2).

These lock the *security contract* the live retriever depends on: what a chunk
carries and what a search is allowed to match. The end-to-end isolation against a
real pgvector lives in ``test_pgvector_integration.py``; here we pin the exact
shapes — including the R1/R3 fix (no null ``agent_id``; ``scope`` + ``$or``).
"""

from __future__ import annotations

from uuid import uuid4

from app.knowledge.metadata import (
    build_conversation_filter,
    build_knowledge_filter,
    chunk_metadata,
)


def test_team_shared_metadata_has_no_agent_id() -> None:
    org, team, src = uuid4(), uuid4(), uuid4()
    meta = chunk_metadata(org_id=org, team_id=team, source_id=src)
    assert meta == {
        "org_id": str(org),
        "team_id": str(team),
        "source_id": str(src),
        "scope": "team",
    }
    assert "agent_id" not in meta  # no null is ever stored (the R1/R3 fix)


def test_agent_private_metadata_carries_agent_id_and_scope() -> None:
    org, team, src, agent = uuid4(), uuid4(), uuid4(), uuid4()
    meta = chunk_metadata(org_id=org, team_id=team, source_id=src, agent_id=agent)
    assert meta["scope"] == "agent"
    assert meta["agent_id"] == str(agent)


def test_filter_scopes_to_org_team_and_shared_or_own_private() -> None:
    org, team, agent = uuid4(), uuid4(), uuid4()
    flt = build_knowledge_filter(
        org_id=org,
        team_id=team,
        agent_id=agent,
        only_specified_sources=False,
        source_ids=(),
    )
    assert flt == {
        "$and": [
            {"org_id": str(org)},
            {"team_id": str(team)},
            {"$or": [{"scope": "team"}, {"agent_id": str(agent)}]},
        ]
    }


def test_filter_restricts_to_specified_sources_when_toggled() -> None:
    org, team, agent = uuid4(), uuid4(), uuid4()
    s1, s2 = uuid4(), uuid4()
    flt = build_knowledge_filter(
        org_id=org,
        team_id=team,
        agent_id=agent,
        only_specified_sources=True,
        source_ids=(s1, s2),
    )
    assert {"source_id": {"$in": [str(s1), str(s2)]}} in flt["$and"]


def test_conversation_attachment_metadata_is_conversation_scoped() -> None:
    """Bug 2 / §8.5.3: a no-team chat upload carries conversation scope, no team/agent."""
    org, conv, src = uuid4(), uuid4(), uuid4()
    meta = chunk_metadata(org_id=org, source_id=src, conversation_id=conv)
    assert meta == {
        "org_id": str(org),
        "source_id": str(src),
        "scope": "conversation",
        "conversation_id": str(conv),
    }
    assert "team_id" not in meta  # no-team chat → no team key
    assert "agent_id" not in meta


def test_team_chat_attachment_keeps_conversation_scope_even_with_team() -> None:
    """A team-chat upload records its team_id but stays ``scope="conversation"`` so it
    never leaks into team ``search_knowledge`` (which matches team/agent scope)."""
    meta = chunk_metadata(
        org_id=uuid4(), source_id=uuid4(), team_id=uuid4(), conversation_id=uuid4()
    )
    assert meta["scope"] == "conversation"
    assert "team_id" in meta


def test_conversation_filter_scopes_to_org_and_conversation() -> None:
    org, conv = uuid4(), uuid4()
    assert build_conversation_filter(org_id=org, conversation_id=conv) == {
        "$and": [{"org_id": str(org)}, {"conversation_id": str(conv)}]
    }


def test_team_filter_cannot_match_conversation_chunks() -> None:
    """§8.5.3 isolation: the team filter's $or is (scope=team OR own agent_id); a
    conversation chunk is scope=conversation with no agent_id, so it can never match."""
    org, team, agent = uuid4(), uuid4(), uuid4()
    flt = build_knowledge_filter(
        org_id=org, team_id=team, agent_id=agent, only_specified_sources=False, source_ids=()
    )
    or_clause = next(c for c in flt["$and"] if "$or" in c)["$or"]
    assert {"scope": "team"} in or_clause
    assert all(clause.get("scope") != "conversation" for clause in or_clause)


def test_only_specified_with_no_sources_matches_nothing() -> None:
    """Restricted-to-specified but none attached → a sentinel that can't match a UUID."""
    flt = build_knowledge_filter(
        org_id=uuid4(),
        team_id=uuid4(),
        agent_id=uuid4(),
        only_specified_sources=True,
        source_ids=(),
    )
    source_clause = next(c for c in flt["$and"] if "source_id" in c)
    assert source_clause["source_id"]["$in"] == ["__no_source__"]
