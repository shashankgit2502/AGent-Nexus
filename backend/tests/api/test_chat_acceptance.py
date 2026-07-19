"""Step-10 acceptance: Chat & Playground backend (BUILD_PLAYBOOK Step 10 "Done when").

Exercised end-to-end against the **real** app + a **real**, migrated Postgres (same
harness as ``test_acceptance.py``): drives the FastAPI app with ``TestClient`` (which
runs the lifespan + default-org seed). Covers ARCH §8.5:

* team chat lightweight → a fast 1-round reply (run completed, not paused);
* team chat Deep Collaborate → the full multi-round loop;
* no-team chat → a single-agent reply with **no run** (stub path, no provider keys);
* playground → ephemeral, **excluded** from conversation history.

Requires the DB up + migrated; marked ``integration``.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.integration


def _wait_for(fn: Callable[[], Any], *, attempts: int = 100, delay: float = 0.05) -> Any:
    """Poll ``fn`` until truthy — team turns now complete asynchronously (ARCH §24.5)."""
    for _ in range(attempts):
        result = fn()
        if result:
            return result
        time.sleep(delay)
    raise AssertionError("condition not met within timeout")


def _drain_to_finish(client: TestClient, conv_id: str, run_id: str) -> list[str]:
    """Subscribe to a conversation turn's live stream until run_finished (§8.5.4)."""
    types: list[str] = []
    with client.websocket_connect(f"/conversations/{conv_id}/stream?run_id={run_id}") as ws:
        while True:
            event = ws.receive_json()
            assert event["run_id"] == run_id
            types.append(event["type"])
            if event["type"] == "run_finished":
                return types


def _drain_events_full(client: TestClient, conv_id: str, run_id: str) -> list[dict]:
    """Drain a conversation turn's live stream, returning the FULL event envelopes."""
    events: list[dict] = []
    with client.websocket_connect(f"/conversations/{conv_id}/stream?run_id={run_id}") as ws:
        while True:
            event = ws.receive_json()
            assert event["run_id"] == run_id
            events.append(event)
            if event["type"] == "run_finished":
                return events


def test_deep_collaborate_streams_mesh_edge_and_debate_events() -> None:
    """Bug 4 verification (4a/4b/4c) against a REAL Deep Collaborate run, end-to-end.

    Drains the **conversation** WS — the exact stream the expanded-from-chat workspace
    subscribes to (4b) — and asserts the events the frontend turns into the mesh viz:

    * a **second round** actually runs (the discussion happens across rounds);
    * **critique** events (sender→target, round-cadenced) → the red critique edges (4a);
    * **responds_to** on round-2 contributions → the accent reply edges (4a);
    * contributions + critiques flow → the **debate thread** populates (4c).

    The frontend half (these shapes → red/accent edges + debate items) is locked by
    ``graph-model.test.ts`` / ``session-reducer.test.ts``; together they verify the
    whole chain: backend emission → WebSocket → store reducer → render.
    """
    with TestClient(app) as client:
        team_id = _make_team_with_agents(client, agents=("Partner", "Finance", "Risk"))
        conv_id = client.post("/conversations", json={"team_id": team_id}).json()["id"]
        sent = client.post(
            f"/conversations/{conv_id}/messages",
            json={"content": "Assess the acquisition.", "deep_collaborate": True},
        ).json()
        events = _drain_events_full(client, conv_id, sent["run"]["id"])
        by_type: dict[str, list[dict]] = {}
        for e in events:
            by_type.setdefault(e["type"], []).append(e)

        # A genuine multi-round discussion ran (not a single independent pass).
        rounds = [e["data"]["round"] for e in by_type.get("round_start", [])]
        assert rounds == [1, 2], f"expected a 2-round discussion, got rounds {rounds}"

        # 4a — critique edges: real sender→target critiques, only at the round boundary.
        critiques = by_type.get("critique", [])
        assert critiques, "no critique events → no red critique edges (4a)"
        assert all(c["data"]["round"] == 2 for c in critiques)  # round-cadenced, never round 1
        assert all({"sender", "target", "severity"} <= c["data"].keys() for c in critiques)

        # 4a — reply edges: round-2 contributions build on prior-round peers.
        replies = [
            c for c in by_type.get("contribution", [])
            if c["data"]["round"] == 2 and c["data"].get("responds_to")
        ]
        assert replies, "no round-2 responds_to → no accent reply edges (4a)"

        # 4c — debate thread source events (contributions + critiques) flow.
        assert len(by_type.get("contribution", [])) >= 6  # 3 agents × 2 rounds
        assert len(critiques) >= 1


def _make_team_with_agents(client: TestClient, *, agents: tuple[str, ...]) -> str:
    team_id = client.post("/teams", json={"name": f"Chat Team {uuid4().hex[:8]}"}).json()["id"]
    for name in agents:
        r = client.post(f"/teams/{team_id}/agents", json={"name": name})
        assert r.status_code == 201, r.text
    return team_id


def test_team_chat_lightweight_returns_fast_reply() -> None:
    with TestClient(app) as client:
        team_id = _make_team_with_agents(client, agents=("Researcher", "Critic"))

        conv = client.post("/conversations", json={"team_id": team_id})
        assert conv.status_code == 201, conv.text
        conv_id = conv.json()["id"]

        # Lightweight (default): 1 round, HITL off. The run executes in the
        # background (ARCH §24.5): the POST returns immediately with a *pending*
        # assistant message + the run/stream to watch live and expand.
        sent = client.post(
            f"/conversations/{conv_id}/messages",
            json={"content": "What is 2 + 2?", "deep_collaborate": False},
        )
        assert sent.status_code == 200, sent.text
        body = sent.json()
        assert body["assistant_message"]["role"] == "assistant"
        assert body["assistant_message"]["content"] is None  # filled when the run finishes
        assert body["assistant_message"]["deep_collaborate"] is False
        # A team turn is run-per-turn: a conversation-owned run + stream, status running.
        run = body["run"]
        assert run is not None
        assert run["status"] == "running"
        assert run["conversation_id"] == conv_id
        assert run["session_id"] is None  # §11.4a run-owner XOR
        run_id = run["id"]
        assert f"run_id={run_id}" in body["stream_url"]

        # The turn's AG-UI stream is delivered live over the conversation WS.
        types = _drain_to_finish(client, conv_id, run_id)
        assert types[0] == "run_start"
        assert "run_finished" in types

        # The pending assistant message is filled from the synthesis (async) — the
        # transcript rehydrate endpoint now returns its content.
        filled = _wait_for(
            lambda: next(
                (
                    m
                    for m in client.get(f"/conversations/{conv_id}/messages").json()
                    if m["role"] == "assistant" and m["content"]
                ),
                None,
            )
        )
        assert filled["run_id"] == run_id


def test_team_chat_deep_collaborate_runs_full_loop() -> None:
    with TestClient(app) as client:
        team_id = _make_team_with_agents(client, agents=("A", "B", "C"))
        conv_id = client.post("/conversations", json={"team_id": team_id}).json()["id"]

        sent = client.post(
            f"/conversations/{conv_id}/messages",
            json={"content": "Plan a product launch.", "deep_collaborate": True},
        )
        assert sent.status_code == 200, sent.text
        body = sent.json()
        # Deep turns run the full multi-round loop in the background (chat HITL off).
        assert body["assistant_message"]["deep_collaborate"] is True
        assert body["run"]["status"] == "running"
        run_id = body["run"]["id"]

        # Watch the live stream: a deep turn opens at least one debate round and ends.
        types = _drain_to_finish(client, conv_id, run_id)
        assert "round_start" in types
        assert "run_finished" in types
        # The assistant message is filled from the synthesis (async).
        _wait_for(
            lambda: any(
                m["role"] == "assistant" and m["content"]
                for m in client.get(f"/conversations/{conv_id}/messages").json()
            )
        )


def test_conversation_messages_rehydrate_in_order() -> None:
    with TestClient(app) as client:
        conv_id = client.post(
            "/conversations", json={"model_ref": {"profile_id": str(uuid4())}}
        ).json()["id"]

        # Empty before any turn.
        empty = client.get(f"/conversations/{conv_id}/messages")
        assert empty.status_code == 200, empty.text
        assert empty.json() == []

        for text in ("first turn", "second turn"):
            posted = client.post(f"/conversations/{conv_id}/messages", json={"content": text})
            assert posted.status_code == 200, posted.text
            # Each no-team turn now runs in the background (ARCH §8.5.4) — wait for
            # its assistant message to be filled before sending the next.
            run_id = posted.json()["run"]["id"]
            _drain_to_finish(client, conv_id, run_id)
            _wait_for(
                lambda cid=conv_id: all(
                    m["content"]
                    for m in client.get(f"/conversations/{cid}/messages").json()
                    if m["role"] == "assistant"
                )
            )

        rows = client.get(f"/conversations/{conv_id}/messages").json()
        # Two turns → four messages (user/assistant × 2), in chronological order.
        assert [m["role"] for m in rows] == ["user", "assistant", "user", "assistant"]
        assert rows[0]["content"] == "first turn"
        assert rows[2]["content"] == "second turn"
        # No-team assistant turns now carry a (single-agent streaming) run (§8.5.4).
        assert rows[1]["run_id"] is not None

        # RLS/ownership: an unknown conversation 404s rather than leaking rows.
        missing = client.get(f"/conversations/{uuid4()}/messages")
        assert missing.status_code == 404, missing.text


def test_no_team_chat_streams_and_replies() -> None:
    with TestClient(app) as client:
        # No team → single-LLM chat. No provider keys configured → deterministic
        # stub reply (both-paths policy), so the flow is exercisable end-to-end.
        conv = client.post(
            "/conversations",
            json={"model_ref": {"profile_id": str(uuid4())}},
        )
        assert conv.status_code == 201, conv.text
        conv_id = conv.json()["id"]

        sent = client.post(f"/conversations/{conv_id}/messages", json={"content": "Hello"})
        assert sent.status_code == 200, sent.text
        body = sent.json()
        # No-team now runs a lightweight single-agent run that streams live (§8.5.4):
        # a pending assistant message + a run + stream_url, no mesh/consensus.
        assert body["assistant_message"]["content"] is None
        assert body["assistant_message"]["run_id"] is not None
        run_id = body["run"]["id"]
        assert body["run"]["status"] == "running"
        assert f"run_id={run_id}" in body["stream_url"]

        # The single-agent trajectory streams over the SAME conversation WS, ending
        # in run_finished — and carries no mesh-only round-debate fan-out beyond one.
        types = _drain_to_finish(client, conv_id, run_id)
        assert types[0] == "run_start"
        assert "contribution" in types
        assert "run_finished" in types

        # The pending assistant message is filled from the reply (async).
        filled = _wait_for(
            lambda: next(
                (
                    m
                    for m in client.get(f"/conversations/{conv_id}/messages").json()
                    if m["role"] == "assistant" and m["content"]
                ),
                None,
            )
        )
        assert filled["run_id"] == run_id


def test_playground_is_excluded_from_history() -> None:
    with TestClient(app) as client:
        team_id = _make_team_with_agents(client, agents=("Solo",))
        pg = client.post("/conversations", json={"team_id": team_id, "is_playground": True})
        assert pg.status_code == 201, pg.text
        pg_id = pg.json()["id"]

        # Excluded from the listing (ARCH §8.5.1)…
        listed = client.get("/conversations").json()
        assert pg_id not in {c["id"] for c in listed}
        # …but still reachable directly by id.
        assert client.get(f"/conversations/{pg_id}").status_code == 200


def test_attachment_upload_transient_then_promote() -> None:
    with TestClient(app) as client:
        team_id = _make_team_with_agents(client, agents=("Solo",))
        conv_id = client.post("/conversations", json={"team_id": team_id}).json()["id"]

        up = client.post(
            f"/conversations/{conv_id}/attachments",
            files={"file": ("notes.txt", b"hello knowledge", "text/plain")},
        )
        assert up.status_code == 201, up.text
        att = up.json()
        assert att["scope"] == "transient"
        assert att["promoted_source_id"] is None
        # Bug 2 / §8.5.3: the upload is now ingested through a conversation-scoped
        # knowledge source (no longer a byte-store stub) — the attachment links to it.
        assert att["source_id"] is not None

        promoted = client.post(
            f"/conversations/{conv_id}/attachments/{att['id']}/save-to-knowledge"
        )
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["scope"] == "knowledge"
        assert promoted.json()["promoted_source_id"] is not None
