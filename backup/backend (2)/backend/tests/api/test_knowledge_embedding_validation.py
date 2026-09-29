"""Ingest-time embedding-model validation (Approach B, Slice 3; ARCH §9.5).

End-to-end against the real app + Postgres: if a team's selected embedding model is
**not** an embedding model (e.g. the user attached a chat model — the exact mistake
behind "No embedding models in the catalog"), registering a source must drive it to
``failed`` with a clear "not an embedding model" reason — not embed documents with the
wrong model. The worker resolves the embedding model *before* loading any document, so
the source fails fast (no network fetch). Skips where there is no DB (``integration``).
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
    for _ in range(attempts):
        result = fn()
        if result:
            return result
        time.sleep(delay)
    raise AssertionError("condition not met within timeout")


def test_source_fails_clearly_when_team_embedding_model_is_a_chat_model() -> None:
    with TestClient(app) as client:
        # A connection + a CHAT catalog model (the wrong type for embeddings).
        conn_id = client.post(
            "/providers/connections",
            json={
                "display_name": f"conn {uuid4().hex[:8]}",
                "provider": "openai_compatible",
                "base_url": "https://example.test/v1",
                "api_key_ref": "sk-test",
            },
        ).json()["id"]
        chat_model = client.post(
            "/providers/catalog",
            json={
                "provider_connection_id": conn_id,
                "display_name": "A Chat Model",
                "model_identifier": f"chat-{uuid4().hex[:6]}",
                "model_type": "chat",
                "supports_tools": True,
            },
        ).json()

        # A team whose embedding model is (wrongly) set to that chat model.
        team_id = client.post("/teams", json={"name": f"KB {uuid4().hex[:8]}"}).json()["id"]
        put = client.put(f"/teams/{team_id}", json={"embedding_model_id": chat_model["id"]})
        assert put.status_code == 200, put.text
        assert put.json()["embedding_model_id"] == chat_model["id"]

        # Register a source → the worker resolves the embedding model first and fails.
        src = client.post(
            f"/teams/{team_id}/knowledge",
            json={"kind": "url", "uri": "https://example.test/doc", "display_name": "doc"},
        )
        assert src.status_code == 201, src.text
        source_id = src.json()["id"]

        def _failed() -> dict[str, Any] | None:
            rows = client.get(f"/teams/{team_id}/knowledge").json()
            row = next((r for r in rows if r["id"] == source_id), None)
            return row if row and row["status"] == "failed" else None

        row = _wait_for(_failed)
        assert "not an embedding model" in (row["error"] or "").lower()
