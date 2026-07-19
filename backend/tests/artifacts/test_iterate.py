"""Slice-3: artifact iteration → new version (ARTIFACTS §10).

Covers the version-snapshot writer (`add_version`), the single-model content
transform (`iterate_artifact_content`, fence-stripped), and the `POST
/artifacts/{id}/iterate` endpoint end-to-end against a real migrated Postgres: a
revise instruction produces v2, advances `current_version`, keeps v1 downloadable
(Canvas history), and the current download returns the revised content.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage
from sqlalchemy import text

from app.api import artifacts as artifacts_api
from app.artifacts.iterator import iterate_artifact_content
from app.artifacts.service import ArtifactService
from app.artifacts.storage import build_storage
from app.core.config import get_settings
from app.db.models import Organization, Run, Session, Team
from app.db.session import AsyncSessionLocal, engine
from app.main import app
from tests.agents._fakes import ScriptedToolCallingModel

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_after_test() -> object:
    yield
    await engine.dispose()


async def _seed_artifact(tmp_path: Path, *, content: str = "print('v1')\n") -> tuple[UUID, UUID]:
    """Seed org → team → session → run + a v1 code artifact; return (org_id, artifact_id)."""
    settings = get_settings()
    async with AsyncSessionLocal() as db:
        org = Organization(name="Iterate Org", slug=f"iter-{uuid4().hex[:10]}")
        db.add(org)
        await db.flush()
        org_id = org.id
        await db.execute(
            text("SELECT set_config('app.current_org', :o, true)"), {"o": str(org_id)}
        )
        team = Team(org_id=org_id, name=f"Iterate {uuid4().hex[:8]}")
        db.add(team)
        await db.flush()
        session = Session(org_id=org_id, team_id=team.id, thread_id=uuid4().hex)
        db.add(session)
        await db.flush()
        run = Run(org_id=org_id, session_id=session.id, query="write code")
        db.add(run)
        await db.flush()
        svc = ArtifactService(db, build_storage(str(tmp_path)), settings, org_id)
        artifact = await svc.create_artifact(
            run_id=run.id,
            kind="code",
            filename="main.py",
            mime_type="text/x-python",
            content=content,
            content_format="code",
        )
        artifact_id = artifact.id
        await db.commit()
    return org_id, artifact_id


async def test_add_version_advances_current_and_keeps_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ARTIFACTS_DIR", str(tmp_path))
    org_id, artifact_id = await _seed_artifact(tmp_path)

    async with AsyncSessionLocal() as db:
        await db.execute(
            text("SELECT set_config('app.current_org', :o, true)"), {"o": str(org_id)}
        )
        svc = ArtifactService(db, build_storage(str(tmp_path)), get_settings(), org_id)
        artifact = await svc.get(artifact_id)
        assert artifact is not None
        await svc.add_version(artifact, content="print('v2')\n")
        await db.commit()

        assert artifact.current_version == 2
        v1 = await svc.get_version(artifact_id, 1)
        v2 = await svc.get_version(artifact_id, 2)
        assert v1 is not None and v1.content == "print('v1')\n"
        assert v2 is not None and v2.content == "print('v2')\n"


async def test_iterate_content_strips_code_fences() -> None:
    # The model wraps in a fence despite instructions → stripped to raw content.
    model = ScriptedToolCallingModel(
        responses=[AIMessage(content="```python\nprint('revised')\n```")]
    )
    out = await iterate_artifact_content(
        model=model,
        kind="code",
        filename="main.py",
        current_content="print('old')",
        instruction="rename to revised",
    )
    assert out == "print('revised')"


async def test_iterate_endpoint_creates_v2_and_keeps_v1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ARTIFACTS_DIR", str(tmp_path))
    org_id, artifact_id = await _seed_artifact(tmp_path)

    # Bypass the live model layer: the iterate model returns the revised content.
    async def _fake_resolver(_db: object, **_kw: object) -> ScriptedToolCallingModel:
        return ScriptedToolCallingModel(responses=[AIMessage(content="print('iterated v2')\n")])

    monkeypatch.setattr(artifacts_api, "resolve_iterate_model", _fake_resolver)

    headers = {"X-Org-Id": str(org_id)}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            f"/artifacts/{artifact_id}/iterate",
            json={"instruction": "rename the greeting"},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["current_version"] == 2
        assert len(body["versions"]) == 2
        # The iterator normalises surrounding blank lines off the model output.
        assert body["preview"] == "print('iterated v2')"

        # Current download → v2; v1 stays downloadable (Canvas history).
        cur = await client.get(f"/artifacts/{artifact_id}/download", headers=headers)
        assert cur.content == b"print('iterated v2')"
        v1 = await client.get(f"/artifacts/{artifact_id}/versions/1/download", headers=headers)
        assert v1.content == b"print('v1')\n"


async def test_iterate_rejects_non_text_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A binary artifact (image) cannot be iterated in v1 — text/code only (§10)."""
    monkeypatch.setattr(get_settings(), "ARTIFACTS_DIR", str(tmp_path))
    org_id, art_id = await _seed_image_artifact(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            f"/artifacts/{art_id}/iterate",
            json={"instruction": "x"},
            headers={"X-Org-Id": str(org_id)},
        )
        assert r.status_code == 400


async def _seed_image_artifact(tmp_path: Path) -> tuple[UUID, UUID]:
    settings = get_settings()
    async with AsyncSessionLocal() as db:
        org = Organization(name="Img Org", slug=f"img-{uuid4().hex[:10]}")
        db.add(org)
        await db.flush()
        org_id = org.id
        await db.execute(
            text("SELECT set_config('app.current_org', :o, true)"), {"o": str(org_id)}
        )
        team = Team(org_id=org_id, name=f"Img {uuid4().hex[:8]}")
        db.add(team)
        await db.flush()
        session = Session(org_id=org_id, team_id=team.id, thread_id=uuid4().hex)
        db.add(session)
        await db.flush()
        run = Run(org_id=org_id, session_id=session.id, query="make image")
        db.add(run)
        await db.flush()
        svc = ArtifactService(db, build_storage(str(tmp_path)), settings, org_id)
        artifact = await svc.create_artifact(
            run_id=run.id,
            kind="image",
            filename="chart.png",
            mime_type="image/png",
            data=b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
        )
        art_id = artifact.id
        await db.commit()
    return org_id, art_id
