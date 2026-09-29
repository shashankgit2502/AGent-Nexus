"""Acceptance for the Bug-5 connection endpoints: test / edit / delete / discover.

Drives the real app + Postgres (like ``test_acceptance``). The network probe is
monkeypatched so the test exercises the routing, validation-state transitions, and
catalog population without reaching a provider.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import api  # noqa: F401 — ensure package import
from app.api import providers
from app.main import app
from app.models_layer.discovery import DiscoveredModel

pytestmark = pytest.mark.integration


@pytest.fixture
def ok_probe(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Stub the network probe to succeed and report two models with capabilities."""

    # Takes the DB session too: ``_probe_connection`` needs it to validate a
    # Workbench connection, which has no model-list endpoint and is instead probed
    # by invoking a model already registered against it.
    async def _fake(_conn: object, _db: object) -> tuple[bool, str, list[DiscoveredModel]]:
        return (
            True,
            "2 models reachable (1 tool-capable)",
            [
                DiscoveredModel(id="org/model-a", supports_tools=True, context_window=128000),
                DiscoveredModel(id="org/model-b", supports_tools=False),
            ],
        )

    monkeypatch.setattr(providers, "_probe_connection", _fake)
    yield


def _make_connection(client: TestClient) -> str:
    r = client.post(
        "/providers/connections",
        json={
            "display_name": f"OpenRouter {uuid4().hex[:8]}",
            "provider": "openrouter",
            "base_url": "https://openrouter.ai/api/v1/chat/completions",
            "api_key_ref": "sk-or-v1-rawkey",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["validated_at"] is None  # starts pending (the original bug state)
    return body["id"]


def test_edit_connection_clears_validation(ok_probe: None) -> None:
    with TestClient(app) as client:
        conn_id = _make_connection(client)
        # Validate it first.
        rt = client.post(f"/providers/connections/{conn_id}/test")
        assert rt.status_code == 200, rt.text
        assert rt.json()["ok"] is True
        assert rt.json()["validated_at"] is not None

        # Editing the key invalidates the prior validation.
        re = client.put(
            f"/providers/connections/{conn_id}",
            json={"api_key_ref": "sk-or-v1-newkey"},
        )
        assert re.status_code == 200, re.text
        assert re.json()["validated_at"] is None


def test_test_connection_marks_validated(ok_probe: None) -> None:
    with TestClient(app) as client:
        conn_id = _make_connection(client)
        rt = client.post(f"/providers/connections/{conn_id}/test")
        assert rt.status_code == 200, rt.text
        body = rt.json()
        assert body["ok"] is True
        assert body["models_found"] == 2
        assert body["validated_at"] is not None


def test_discover_populates_catalog_with_capabilities(ok_probe: None) -> None:
    with TestClient(app) as client:
        conn_id = _make_connection(client)
        rd = client.post(f"/providers/connections/{conn_id}/discover")
        assert rd.status_code == 200, rd.text
        models = rd.json()
        assert {m["model_identifier"] for m in models} == {"org/model-a", "org/model-b"}
        # Capabilities are persisted from discovery (the §9.3 gate must pass for
        # the tool-capable model) — the regression: this used to be all-false.
        by_id = {m["model_identifier"]: m for m in models}
        assert by_id["org/model-a"]["supports_tools"] is True
        assert by_id["org/model-a"]["context_window"] == 128000
        assert by_id["org/model-b"]["supports_tools"] is False

        # Re-discover is an idempotent UPSERT: no duplicate rows, capabilities
        # refreshed. The catalog still holds exactly the two models.
        rd2 = client.post(f"/providers/connections/{conn_id}/discover")
        assert rd2.status_code == 200
        assert {m["model_identifier"] for m in rd2.json()} == {"org/model-a", "org/model-b"}
        listed = client.get("/providers/catalog?supports_tools=true").json()
        assert [
            m["model_identifier"] for m in listed if m["provider_connection_id"] == conn_id
        ] == ["org/model-a"]


def test_delete_connection(ok_probe: None) -> None:
    with TestClient(app) as client:
        conn_id = _make_connection(client)
        rdel = client.delete(f"/providers/connections/{conn_id}")
        assert rdel.status_code == 204, rdel.text
        # Gone from the list and a second delete 404s.
        assert all(c["id"] != conn_id for c in client.get("/providers/connections").json())
        assert client.delete(f"/providers/connections/{conn_id}").status_code == 404


# ── ITEM 1: master-detail connection models (GET /connections/{id}/models) ──────
def test_connection_models_search_filter_and_paginate(ok_probe: None) -> None:
    """The master-detail endpoint scopes to one connection, supports ?q search,
    the supports_tools gate filter, and limit/offset paging with a stable total."""
    with TestClient(app) as client:
        conn_id = _make_connection(client)
        # discover seeds two models: org/model-a (tools) + org/model-b (no tools).
        assert client.post(f"/providers/connections/{conn_id}/discover").status_code == 200

        full = client.get(f"/providers/connections/{conn_id}/models")
        assert full.status_code == 200, full.text
        body = full.json()
        assert body["total"] == 2
        assert {m["model_identifier"] for m in body["items"]} == {"org/model-a", "org/model-b"}

        # ?q matches identifier/display name (case-insensitive).
        q = client.get(f"/providers/connections/{conn_id}/models", params={"q": "MODEL-A"}).json()
        assert q["total"] == 1
        assert q["items"][0]["model_identifier"] == "org/model-a"

        # ?supports_tools=true applies the §9.3 mesh gate.
        tools = client.get(
            f"/providers/connections/{conn_id}/models", params={"supports_tools": "true"}
        ).json()
        assert [m["model_identifier"] for m in tools["items"]] == ["org/model-a"]

        # Paging: one row per page, total still reflects the full match set.
        page = client.get(
            f"/providers/connections/{conn_id}/models", params={"limit": 1, "offset": 0}
        ).json()
        assert page["total"] == 2 and len(page["items"]) == 1
        assert page["limit"] == 1 and page["offset"] == 0


def test_connection_models_unknown_connection_404() -> None:
    with TestClient(app) as client:
        assert client.get(f"/providers/connections/{uuid4()}/models").status_code == 404


# ── Manual catalog registration (POST /catalog) ────────────────────────────────
def test_create_catalog_model_duplicate_conflicts(ok_probe: None) -> None:
    """Manually registering a model that already has a live row for the connection
    returns 409 — not the asyncpg ``UniqueViolationError``→500 that the UI saw as
    "Failed to fetch". A previously soft-deleted model can still be re-added, so the
    guard mirrors the partial unique index (live rows only), it does not blanket-block."""
    with TestClient(app) as client:
        conn_id = _make_connection(client)
        payload = {
            "provider_connection_id": conn_id,
            "display_name": "llama nemotron embed",
            "model_identifier": "nvidia/llama-nemotron-embed-1b-v2",
            "model_type": "embedding",
            "context_window": 128000,
        }
        first = client.post("/providers/catalog", json=payload)
        assert first.status_code == 201, first.text
        model_id = first.json()["id"]

        # Re-registering the same (connection, identifier) now 409s instead of 500ing.
        dup = client.post("/providers/catalog", json=payload)
        assert dup.status_code == 409, dup.text
        assert "already registered" in dup.json()["detail"]

        # Soft-delete frees the partial-index slot → the model can be re-added (201).
        assert client.delete(f"/providers/catalog/{model_id}").status_code == 204
        readd = client.post("/providers/catalog", json=payload)
        assert readd.status_code == 201, readd.text


# ── Approach B: embedding classification (discover + PATCH reclassify) ──────────
def test_discover_classifies_embedding_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Discovery no longer hardcodes chat: an embedding-typed discovered model lands
    in the catalog as ``model_type='embedding'`` (so the team picker can list it)."""

    async def _embed_probe(_conn: object, _db: object) -> tuple[bool, str, list[DiscoveredModel]]:
        return (True, "1 model", [DiscoveredModel(id="nv/nemo-embed", model_type="embedding")])

    monkeypatch.setattr(providers, "_probe_connection", _embed_probe)
    with TestClient(app) as client:
        conn_id = _make_connection(client)
        assert client.post(f"/providers/connections/{conn_id}/discover").status_code == 200
        catalog = client.get("/providers/catalog").json()
        row = next(m for m in catalog if m["model_identifier"] == "nv/nemo-embed")
        assert row["model_type"] == "embedding"


def test_patch_catalog_model_reclassifies_to_embedding(ok_probe: None) -> None:
    """A mislabeled chat row can be flipped to embedding without delete+re-add; flipping
    to embedding also clears supports_tools (embeddings are not tool-callers)."""
    with TestClient(app) as client:
        conn_id = _make_connection(client)
        created = client.post(
            "/providers/catalog",
            json={
                "provider_connection_id": conn_id,
                "display_name": "nemotron embed",
                "model_identifier": "nemotron:embed",
                "model_type": "chat",
                "supports_tools": True,
            },
        )
        assert created.status_code == 201, created.text
        model_id = created.json()["id"]

        patched = client.patch(f"/providers/catalog/{model_id}", json={"model_type": "embedding"})
        assert patched.status_code == 200, patched.text
        body = patched.json()
        assert body["model_type"] == "embedding"
        assert body["supports_tools"] is False  # embeddings are not tool-callers

        # It now appears as an embedding model in the whole-org catalog (picker source).
        catalog = client.get("/providers/catalog").json()
        assert any(m["id"] == model_id and m["model_type"] == "embedding" for m in catalog)


def test_patch_unknown_catalog_model_404() -> None:
    with TestClient(app) as client:
        r = client.patch(f"/providers/catalog/{uuid4()}", json={"model_type": "embedding"})
        assert r.status_code == 404


# ── ITEM 1: inference-profile delete (DELETE /profiles/{id}) ────────────────────
def _make_profile(client: TestClient) -> str:
    r = client.post("/providers/profiles", json={"name": f"Profile {uuid4().hex[:8]}"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_delete_profile_success() -> None:
    with TestClient(app) as client:
        profile_id = _make_profile(client)
        rdel = client.delete(f"/providers/profiles/{profile_id}")
        assert rdel.status_code == 204, rdel.text
        assert all(p["id"] != profile_id for p in client.get("/providers/profiles").json())
        # Second delete 404s (soft-deleted rows are excluded).
        assert client.delete(f"/providers/profiles/{profile_id}").status_code == 404


def test_delete_profile_blocked_when_in_use() -> None:
    """A profile referenced by a live agent cannot be deleted — 409 names the
    agents so the UI can guide reassignment; the profile is left intact (no orphan)."""
    with TestClient(app) as client:
        profile_id = _make_profile(client)
        team_id = client.post("/teams", json={"name": f"Team {uuid4().hex[:6]}"}).json()["id"]
        agent = client.post(
            f"/teams/{team_id}/agents", json={"name": "Researcher", "profile_id": profile_id}
        )
        assert agent.status_code == 201, agent.text

        rdel = client.delete(f"/providers/profiles/{profile_id}")
        assert rdel.status_code == 409, rdel.text
        detail = rdel.json()["detail"]
        assert any(a["name"] == "Researcher" for a in detail["agents"])
        # Still present — nothing was orphaned or silently nulled.
        assert any(p["id"] == profile_id for p in client.get("/providers/profiles").json())
