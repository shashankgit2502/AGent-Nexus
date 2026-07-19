"""Acceptance for the Memory Explorer CRUD endpoints (ARCH §14, FRONTEND_SPEC §14).

Drives the real app + Postgres (like ``test_acceptance``). Memory **records** are
normally written by the post-run consolidation step (ARCH §25.3, covered by the
offline ``tests/memory`` unit tests); here we seed them directly into the same live
``Store`` the endpoints read — via the real :class:`~app.memory.items.MemoryItemStore`
(R2) under the org-prefixed namespace (§25.1) — so the list / search / pin / delete
routes are exercised end-to-end against the DB without needing a live model.

Requires the DB up and migrated; marked ``integration`` so it is excluded where
there is no Postgres.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.memory.items import MemoryItemStore

pytestmark = pytest.mark.integration


def _make_team_and_agent(client: TestClient) -> tuple[UUID, UUID, UUID]:
    """Create a team + one agent via the API; return (org_id, team_id, agent_id)."""
    team_id = client.post("/teams", json={"name": f"Mem {uuid4().hex[:8]}"}).json()["id"]
    agent = client.post(f"/teams/{team_id}/agents", json={"name": "Researcher"}).json()
    org_id = client.app.state.default_org_id  # seeded by the lifespan
    return UUID(str(org_id)), UUID(team_id), UUID(agent["id"])


def test_list_search_filter_pin_delete_memory_records() -> None:
    with TestClient(app) as client:
        org_id, team_id, agent_id = _make_team_and_agent(client)

        # Seed records straight into the live Store the endpoint reads.
        store = MemoryItemStore(client.app.state.memory_store)
        a = store.write_item(
            org_id=org_id, team_id=team_id, agent_id=agent_id,
            kind="fact", content="prefers pgvector over FAISS",
        )
        store.write_item(
            org_id=org_id, team_id=team_id, agent_id=agent_id,
            kind="experience", content="last run chose a hybrid index",
        )

        # List → both records, total reported.
        listed = client.get(f"/agents/{agent_id}/memories")
        assert listed.status_code == 200, listed.text
        body = listed.json()
        assert body["total"] == 2
        assert {i["content"] for i in body["items"]} == {
            "prefers pgvector over FAISS",
            "last run chose a hybrid index",
        }
        assert body["limit"] == 50 and body["offset"] == 0

        # Search (substring) and kind filter narrow the list.
        hits = client.get(f"/agents/{agent_id}/memories", params={"q": "pgvector"}).json()
        assert [i["content"] for i in hits["items"]] == ["prefers pgvector over FAISS"]
        facts = client.get(f"/agents/{agent_id}/memories", params={"kind": "fact"}).json()
        assert facts["total"] == 1

        # Pin the second record → it sorts first regardless of recency.
        pin = client.patch(f"/agents/{agent_id}/memories/{a.id}", json={"pinned": True})
        assert pin.status_code == 200, pin.text
        assert pin.json()["pinned"] is True
        ordered = client.get(f"/agents/{agent_id}/memories").json()["items"]
        assert ordered[0]["id"] == str(a.id)

        # Delete → 204, then gone; deleting again is a clean 404 (idempotent).
        assert client.delete(f"/agents/{agent_id}/memories/{a.id}").status_code == 204
        remaining = client.get(f"/agents/{agent_id}/memories").json()
        assert all(i["id"] != str(a.id) for i in remaining["items"])
        assert client.delete(f"/agents/{agent_id}/memories/{a.id}").status_code == 404


def test_pin_unknown_record_is_404() -> None:
    with TestClient(app) as client:
        _org, _team, agent_id = _make_team_and_agent(client)
        r = client.patch(f"/agents/{agent_id}/memories/{uuid4()}", json={"pinned": True})
        assert r.status_code == 404


def test_memories_for_unknown_agent_is_404() -> None:
    with TestClient(app) as client:
        assert client.get(f"/agents/{uuid4()}/memories").status_code == 404


def test_other_org_cannot_read_agent_memories() -> None:
    """Org isolation: the agent's memories are invisible to a different org (§25.1/§11.7)."""
    with TestClient(app) as client:
        _org, _team, agent_id = _make_team_and_agent(client)
        other = client.get(
            f"/agents/{agent_id}/memories", headers={"X-Org-Id": str(uuid4())}
        )
        assert other.status_code == 404
