"""End-to-end acceptance for the knowledge ingestion spine (ITEM 2 Slice A).

Drives the real FastAPI app + Postgres + the async ingestion worker (the piece that
was missing — ITEM 2 root-cause #1). Proves the lifecycle that was broken:

* a real file upload goes ``pending → ingesting → ready`` with ``chunk_count > 0``;
* deleting the source removes it *and* its vector chunks (no stale RAG);
* a misconfigured embedding model produces ``failed`` + a precise error, never a
  silent forever-``pending`` (root-cause #3, the honest replacement).

Embeddings are stubbed with ``DeterministicFakeEmbedding`` so the worker's real
resolve→embed→PGVector path runs without any provider/API key (mirrors the existing
pgvector integration test). Skips when Postgres is unreachable.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.embeddings import DeterministicFakeEmbedding

from app.main import app
from app.models_layer.embeddings import EmbeddingsResolver

pytestmark = pytest.mark.integration

_EMBED_DIM = 32


def _wait_for(fn: Callable[[], Any], *, attempts: int = 100, delay: float = 0.05) -> Any:
    """Poll ``fn`` until truthy (ingestion runs on a background task, §24.5)."""
    for _ in range(attempts):
        result = fn()
        if result:
            return result
        time.sleep(delay)
    raise AssertionError("condition not met within timeout")


def _make_connection(client: TestClient) -> str:
    r = client.post(
        "/providers/connections",
        json={
            "display_name": f"OpenAI {uuid4().hex[:8]}",
            "provider": "openai",
            "api_key_ref": "sk-local-rawkey",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _make_catalog_model(client: TestClient, conn_id: str, *, model_type: str) -> str:
    r = client.post(
        "/providers/catalog",
        json={
            "provider_connection_id": conn_id,
            "display_name": f"{model_type}-{uuid4().hex[:6]}",
            "model_identifier": f"{model_type}-model",
            "model_type": model_type,
            "source": "manual",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _make_team(client: TestClient, *, embedding_model_id: str | None) -> str:
    r = client.post(
        "/teams",
        json={"name": f"KB Team {uuid4().hex[:8]}", "embedding_model_id": embedding_model_id},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _source(client: TestClient, team_id: str, source_id: str) -> dict[str, Any] | None:
    for s in client.get(f"/teams/{team_id}/knowledge").json():
        if s["id"] == source_id:
            return s
    return None


def _await_terminal(client: TestClient, team_id: str, source_id: str) -> dict[str, Any]:
    """Poll until the source reaches a terminal status (ready/failed); return it."""

    def terminal() -> dict[str, Any] | None:
        s = _source(client, team_id, source_id)
        return s if s and s["status"] in ("ready", "failed") else None

    return _wait_for(terminal)


def test_upload_ingests_to_ready_then_delete_removes_it(monkeypatch: pytest.MonkeyPatch) -> None:
    # Stub embeddings so the real resolve→embed→PGVector path runs without an API key.
    monkeypatch.setattr(
        EmbeddingsResolver,
        "resolve",
        lambda self, model_id: DeterministicFakeEmbedding(size=_EMBED_DIM),
    )
    with TestClient(app) as client:
        conn = _make_connection(client)
        embed_model = _make_catalog_model(client, conn, model_type="embedding")
        team_id = _make_team(client, embedding_model_id=embed_model)

        # Upload a real markdown file (bytes, not a bare URI — root-cause #2).
        body = b"# Playbook\n\n" + b"NEX AGI mesh consensus. " * 80
        up = client.post(
            f"/teams/{team_id}/knowledge/upload",
            files={"file": ("playbook.md", body, "text/markdown")},
        )
        assert up.status_code == 201, up.text
        source_id = up.json()["id"]
        assert up.json()["status"] == "pending"

        # The worker drives it to ready with chunks (was: stuck pending · 0 chunks).
        ready = _await_terminal(client, team_id, source_id)
        assert ready["status"] == "ready", ready
        assert ready["chunk_count"] > 0

        # Delete removes the source (and its vectors) — gone from the list.
        d = client.delete(f"/teams/{team_id}/knowledge/{source_id}")
        assert d.status_code == 204, d.text
        assert _source(client, team_id, source_id) is None


def test_upload_docx_office_format_ingests_to_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    # Slice B: a real .docx flows through the same worker spine (upload → office
    # loader → split → embed → ready), proving the loader registry seam end-to-end.
    monkeypatch.setattr(
        EmbeddingsResolver,
        "resolve",
        lambda self, model_id: DeterministicFakeEmbedding(size=_EMBED_DIM),
    )
    import io

    from docx import Document as DocxDocument

    d = DocxDocument()
    for _ in range(20):
        d.add_paragraph("Quarterly strategy notes for the NEX AGI knowledge base.")
    buf = io.BytesIO()
    d.save(buf)

    with TestClient(app) as client:
        conn = _make_connection(client)
        embed_model = _make_catalog_model(client, conn, model_type="embedding")
        team_id = _make_team(client, embedding_model_id=embed_model)

        up = client.post(
            f"/teams/{team_id}/knowledge/upload",
            files={
                "file": (
                    "strategy.docx",
                    buf.getvalue(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        assert up.status_code == 201, up.text
        ready = _await_terminal(client, team_id, up.json()["id"])
        assert ready["status"] == "ready", ready
        assert ready["chunk_count"] > 0


def test_upload_image_ingests_via_vision_caption(monkeypatch: pytest.MonkeyPatch) -> None:
    # Slice C: a PNG with an org-default vision model configured ingests by captioning
    # the image (stubbed — no real vision call), proving the image path end-to-end.
    monkeypatch.setattr(
        EmbeddingsResolver,
        "resolve",
        lambda self, model_id: DeterministicFakeEmbedding(size=_EMBED_DIM),
    )
    # Stub the captioner factory so the resolved vision model is never actually called.
    from app.knowledge import image_processing

    monkeypatch.setattr(
        image_processing,
        "make_vision_captioner",
        lambda model: (lambda data, mime: "A diagram of the NEX AGI mesh topology."),
    )

    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (16, 16), (40, 120, 200)).save(buf, format="PNG")

    with TestClient(app) as client:
        conn = _make_connection(client)
        embed_model = _make_catalog_model(client, conn, model_type="embedding")
        # An org-default vision model: a chat model flagged supports_vision.
        r = client.post(
            "/providers/catalog",
            json={
                "provider_connection_id": conn,
                "display_name": f"vision-{uuid4().hex[:6]}",
                "model_identifier": "vision-model",
                "model_type": "chat",
                "supports_vision": True,
                "source": "manual",
            },
        )
        assert r.status_code == 201, r.text
        team_id = _make_team(client, embedding_model_id=embed_model)

        up = client.post(
            f"/teams/{team_id}/knowledge/upload",
            files={"file": ("diagram.png", buf.getvalue(), "image/png")},
        )
        assert up.status_code == 201, up.text
        ready = _await_terminal(client, team_id, up.json()["id"])
        assert ready["status"] == "ready", ready
        assert ready["chunk_count"] > 0  # the caption text was chunked + embedded


def test_misconfigured_embedding_model_fails_with_reason() -> None:
    # team points its embedding model at a CHAT model → the real resolver rejects it
    # (NotAnEmbeddingModel) → the source must end 'failed' with a precise error,
    # never silently stuck pending (ITEM 2 root-cause #3).
    with TestClient(app) as client:
        conn = _make_connection(client)
        chat_model = _make_catalog_model(client, conn, model_type="chat")
        team_id = _make_team(client, embedding_model_id=chat_model)

        up = client.post(
            f"/teams/{team_id}/knowledge/upload",
            files={"file": ("note.txt", b"some content to embed", "text/plain")},
        )
        assert up.status_code == 201, up.text
        source_id = up.json()["id"]

        terminal = _await_terminal(client, team_id, source_id)
        assert terminal["status"] == "failed", terminal
        assert terminal["chunk_count"] == 0
        assert "embedding" in (terminal["error"] or "").lower()
