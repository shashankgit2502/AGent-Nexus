"""MemoryItemStore tests (ARCH §14 / §25.1, FRONTEND_SPEC §14).

The Memory Explorer's per-item record layer: one LangGraph ``Store`` key per memory,
each with its own kind / pinned / timestamp metadata, supporting list, keyword
search, delete, and pin. Exercised over the real ``BaseStore`` primitive (R2) on a
``langgraph.store.memory.InMemoryStore`` so the tests run offline and deterministic.

Namespaces are org-prefixed (Item 3 decision, §25.1), so every call carries
``org_id`` — the top tenant (TECHNICAL §11.0).
"""

from __future__ import annotations

from uuid import uuid4

from langgraph.store.memory import InMemoryStore

from app.memory.items import MemoryItem, MemoryItemStore


def _store() -> MemoryItemStore:
    return MemoryItemStore(InMemoryStore())


def test_write_then_list_roundtrips() -> None:
    svc = _store()
    org, team, agent = uuid4(), uuid4(), uuid4()
    item = svc.write_item(
        org_id=org, team_id=team, agent_id=agent, kind="fact", content="prefers pgvector"
    )
    assert isinstance(item, MemoryItem)
    listed = svc.list_items(org_id=org, team_id=team, agent_id=agent)
    assert [i.content for i in listed] == ["prefers pgvector"]
    assert listed[0].id == item.id
    assert listed[0].kind == "fact"
    assert listed[0].pinned is False


def test_records_isolated_per_agent() -> None:
    store = InMemoryStore()
    svc = MemoryItemStore(store)
    org, team, agent_1, agent_2 = uuid4(), uuid4(), uuid4(), uuid4()
    svc.write_item(org_id=org, team_id=team, agent_id=agent_1, kind="fact", content="agent-1 only")
    assert svc.list_items(org_id=org, team_id=team, agent_id=agent_2) == []
    assert [i.content for i in svc.list_items(org_id=org, team_id=team, agent_id=agent_1)] == [
        "agent-1 only"
    ]


def test_records_isolated_per_org() -> None:
    store = InMemoryStore()
    svc = MemoryItemStore(store)
    org_1, org_2, team, agent = uuid4(), uuid4(), uuid4(), uuid4()
    # Same team+agent ids under a DIFFERENT org must not leak (org is the top tenant).
    svc.write_item(org_id=org_1, team_id=team, agent_id=agent, kind="fact", content="org-1 only")
    assert svc.list_items(org_id=org_2, team_id=team, agent_id=agent) == []
    assert len(svc.list_items(org_id=org_1, team_id=team, agent_id=agent)) == 1


def test_list_filters_by_kind() -> None:
    svc = _store()
    org, team, agent = uuid4(), uuid4(), uuid4()
    svc.write_item(org_id=org, team_id=team, agent_id=agent, kind="fact", content="a fact")
    svc.write_item(
        org_id=org, team_id=team, agent_id=agent, kind="experience", content="an experience"
    )
    facts = svc.list_items(org_id=org, team_id=team, agent_id=agent, kind="fact")
    assert [i.content for i in facts] == ["a fact"]


def test_pinned_items_sort_first_then_newest() -> None:
    svc = _store()
    org, team, agent = uuid4(), uuid4(), uuid4()
    first = svc.write_item(org_id=org, team_id=team, agent_id=agent, kind="fact", content="first")
    svc.write_item(org_id=org, team_id=team, agent_id=agent, kind="fact", content="second")
    third = svc.write_item(org_id=org, team_id=team, agent_id=agent, kind="fact", content="third")
    # Pin the OLDEST so we prove pin beats recency, and recency orders the rest.
    svc.set_pinned(org_id=org, team_id=team, agent_id=agent, item_id=first.id, pinned=True)
    order = [i.content for i in svc.list_items(org_id=org, team_id=team, agent_id=agent)]
    assert order == ["first", "third", "second"]
    assert third.created_at >= first.created_at


def test_set_pinned_toggles_and_preserves_fields() -> None:
    svc = _store()
    org, team, agent = uuid4(), uuid4(), uuid4()
    item = svc.write_item(org_id=org, team_id=team, agent_id=agent, kind="fact", content="keep me")
    pinned = svc.set_pinned(org_id=org, team_id=team, agent_id=agent, item_id=item.id, pinned=True)
    assert pinned.pinned is True
    assert pinned.id == item.id
    assert pinned.content == "keep me"
    assert pinned.created_at == item.created_at
    unpinned = svc.set_pinned(
        org_id=org, team_id=team, agent_id=agent, item_id=item.id, pinned=False
    )
    assert unpinned.pinned is False


def test_delete_removes_the_record() -> None:
    svc = _store()
    org, team, agent = uuid4(), uuid4(), uuid4()
    item = svc.write_item(
        org_id=org, team_id=team, agent_id=agent, kind="fact", content="temporary"
    )
    assert svc.delete_item(org_id=org, team_id=team, agent_id=agent, item_id=item.id) is True
    assert svc.list_items(org_id=org, team_id=team, agent_id=agent) == []
    # Deleting an absent record reports False (not an error) — idempotent delete.
    assert svc.delete_item(org_id=org, team_id=team, agent_id=agent, item_id=item.id) is False


def test_get_absent_returns_none() -> None:
    svc = _store()
    assert (
        svc.get_item(org_id=uuid4(), team_id=uuid4(), agent_id=uuid4(), item_id=uuid4()) is None
    )


def test_search_matches_content_substring_case_insensitive() -> None:
    svc = _store()
    org, team, agent = uuid4(), uuid4(), uuid4()
    svc.write_item(
        org_id=org, team_id=team, agent_id=agent, kind="fact", content="prefers PGVector over FAISS"
    )
    svc.write_item(
        org_id=org, team_id=team, agent_id=agent, kind="fact", content="likes strong typing"
    )
    hits = svc.list_items(org_id=org, team_id=team, agent_id=agent, query="pgvector")
    assert [i.content for i in hits] == ["prefers PGVector over FAISS"]


def test_list_paginates() -> None:
    svc = _store()
    org, team, agent = uuid4(), uuid4(), uuid4()
    for n in range(5):
        svc.write_item(org_id=org, team_id=team, agent_id=agent, kind="fact", content=f"item-{n}")
    page = svc.list_items(org_id=org, team_id=team, agent_id=agent, limit=2, offset=0)
    assert len(page) == 2
    page_2 = svc.list_items(org_id=org, team_id=team, agent_id=agent, limit=2, offset=2)
    assert len(page_2) == 2
    # The two pages are disjoint (no overlap from a stable ordering).
    assert {i.id for i in page}.isdisjoint({i.id for i in page_2})


def test_list_page_returns_total_after_filtering() -> None:
    svc = _store()
    org, team, agent = uuid4(), uuid4(), uuid4()
    for n in range(4):
        svc.write_item(org_id=org, team_id=team, agent_id=agent, kind="fact", content=f"keep-{n}")
    svc.write_item(org_id=org, team_id=team, agent_id=agent, kind="experience", content="other")
    # total reflects the kind filter, before paging; the page respects limit/offset.
    page, total = svc.list_page(
        org_id=org, team_id=team, agent_id=agent, kind="fact", limit=2, offset=0
    )
    assert total == 4
    assert len(page) == 2
