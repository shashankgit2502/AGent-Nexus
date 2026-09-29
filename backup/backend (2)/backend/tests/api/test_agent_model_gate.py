"""Config-time §9.3 gate on agent create/update (Slice 3) — RCA prevention.

Pushes the tool-calling hard gate forward to the Agent Builder: assigning a non-tool
model to a peer agent is rejected with 422 at save time, so the misconfiguration that
caused the all-stub run (team had agents on ``nvidia/nemotron-3-ultra-550b-a55b``,
``supports_tools=false``) cannot be persisted in the first place.

Drives the real app + a real migrated Postgres (same harness as
``test_providers_endpoints``); the network probe is stubbed so discovery populates the
catalog with one tool-capable and one non-tool model without reaching a provider.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import providers
from app.main import app
from app.models_layer.discovery import DiscoveredModel

pytestmark = pytest.mark.integration


@pytest.fixture
def ok_probe(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Stub the probe: one tool-capable (model-a) and one non-tool (model-b) model."""

    # Takes the DB session too: ``_probe_connection`` needs it to validate a
    # Workbench connection, which has no model-list endpoint and is instead probed
    # by invoking a model already registered against it.
    async def _fake(_conn: object, _db: object) -> tuple[bool, str, list[DiscoveredModel]]:
        return (
            True,
            "2 models reachable (1 tool-capable)",
            [
                DiscoveredModel(id="org/tool-model", supports_tools=True, context_window=128000),
                DiscoveredModel(id="org/notool-model", supports_tools=False),
            ],
        )

    monkeypatch.setattr(providers, "_probe_connection", _fake)
    yield


def _seed_models(client: TestClient) -> tuple[str, str]:
    """Create a connection, discover its catalog, return (tool_model_id, notool_model_id)."""
    conn = client.post(
        "/providers/connections",
        json={
            "display_name": f"OpenRouter {uuid4().hex[:8]}",
            "provider": "openrouter",
            "base_url": "https://openrouter.ai/api/v1/chat/completions",
            "api_key_ref": "sk-or-v1-rawkey",
        },
    )
    assert conn.status_code == 201, conn.text
    discovered = client.post(f"/providers/connections/{conn.json()['id']}/discover")
    assert discovered.status_code == 200, discovered.text
    by_tools = {m["supports_tools"]: m["id"] for m in discovered.json()}
    return by_tools[True], by_tools[False]


def _profile(client: TestClient, *, name: str, model_id: str | None) -> str:
    r = client.post("/providers/profiles", json={"name": name, "default_model_id": model_id})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _team(client: TestClient) -> str:
    r = client.post("/teams", json={"name": f"Gate Team {uuid4().hex[:8]}"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_create_agent_with_non_tool_profile_is_rejected(ok_probe: None) -> None:
    with TestClient(app) as client:
        _tool, notool = _seed_models(client)
        notool_profile = _profile(client, name="Nemotron", model_id=notool)
        team = _team(client)

        r = client.post(
            f"/teams/{team}/agents",
            json={"name": "Financial DD Lead", "profile_id": notool_profile},
        )
        assert r.status_code == 422, r.text
        assert "does not support tool calling" in r.json()["detail"]
        # Nothing was persisted — the misconfigured agent never reaches the roster.
        assert client.get(f"/teams/{team}/agents").json() == []


def test_create_agent_with_tool_capable_profile_succeeds(ok_probe: None) -> None:
    with TestClient(app) as client:
        tool, _notool = _seed_models(client)
        tool_profile = _profile(client, name="Minimax", model_id=tool)
        team = _team(client)

        r = client.post(
            f"/teams/{team}/agents",
            json={"name": "Engagement Partner", "profile_id": tool_profile},
        )
        assert r.status_code == 201, r.text


def test_non_tool_override_overrides_a_tool_capable_profile(ok_probe: None) -> None:
    """The override (ARCH Q1) is the effective model, so a non-tool override is rejected."""
    with TestClient(app) as client:
        tool, notool = _seed_models(client)
        tool_profile = _profile(client, name="Minimax", model_id=tool)
        team = _team(client)

        r = client.post(
            f"/teams/{team}/agents",
            json={"name": "Risk", "profile_id": tool_profile, "override_model_id": notool},
        )
        assert r.status_code == 422, r.text


def test_agent_without_a_model_is_allowed(ok_probe: None) -> None:
    """No profile/override → nothing to gate (the missing-model case is handled elsewhere)."""
    with TestClient(app) as client:
        team = _team(client)
        r = client.post(f"/teams/{team}/agents", json={"name": "Draft"})
        assert r.status_code == 201, r.text


def test_update_agent_to_non_tool_profile_is_rejected(ok_probe: None) -> None:
    with TestClient(app) as client:
        tool, notool = _seed_models(client)
        tool_profile = _profile(client, name="Minimax", model_id=tool)
        notool_profile = _profile(client, name="Nemotron", model_id=notool)
        team = _team(client)
        created = client.post(
            f"/teams/{team}/agents",
            json={"name": "Sector Specialist", "profile_id": tool_profile},
        )
        assert created.status_code == 201, created.text
        agent_id = created.json()["id"]

        r = client.put(f"/agents/{agent_id}", json={"profile_id": notool_profile})
        assert r.status_code == 422, r.text
        # The agent keeps its valid profile — the rejected patch did not mutate it.
        assert client.get(f"/agents/{agent_id}").json()["profile_id"] == tool_profile
