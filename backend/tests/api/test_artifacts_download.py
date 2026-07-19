"""Slice-1 acceptance: artifact storage + signed, RLS-scoped download (ARTIFACTS.md §18.1).

Drives the **real** app endpoints against a **real**, migrated Postgres (the slice's
"Done when": extend ``artifacts``, add ``artifact_versions``, wire object storage, and
serve ``GET /artifacts/{id}/download`` with a signed URL + RLS). Rows are seeded
directly through the org-scoped session (artifacts are created by tools, not an API —
§10), then the read/download routes are exercised over ASGI.

Covered:
* text artifact inlines in ``content``; binary artifact spills to object storage (§7);
* download via **signed token** (no auth header) and via **authenticated** org context;
* RLS: another org cannot read or download the artifact (§15);
* a tampered token is refused; a specific version downloads;
* the per-artifact size cap is enforced (§15).
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.artifacts.service import ArtifactService, ArtifactTooLarge
from app.artifacts.storage import build_storage
from app.core.config import get_settings
from app.db.models import Artifact, Organization, Run, Session, Team
from app.db.session import AsyncSessionLocal, engine
from app.main import app

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_after_test() -> object:
    """Dispose the shared async engine's pool inside each test's own event loop.

    These tests talk to Postgres directly (no sync ``TestClient`` lifespan to manage
    the loop), and pytest-asyncio gives each test a fresh loop. Without this, the
    module-level engine's pooled asyncpg connections outlive their creating loop and
    are GC'd against a closed loop ("Event loop is closed"). Disposing here closes
    them cleanly while the loop is still alive; the next test re-pools lazily.
    """
    yield
    await engine.dispose()


async def _set_org(db: object, org_id: UUID) -> None:
    await db.execute(  # type: ignore[attr-defined]
        text("SELECT set_config('app.current_org', :o, true)"), {"o": str(org_id)}
    )


async def _make_org() -> UUID:
    """Create a fresh organization (the tenant root has no RLS) and return its id."""
    async with AsyncSessionLocal() as db:
        org = Organization(name="Artifact Test Org", slug=f"art-{uuid4().hex[:10]}")
        db.add(org)
        await db.flush()
        org_id = org.id
        await db.commit()
    return org_id


async def _seed_run(org_id: UUID) -> UUID:
    """Seed team → session → run under ``org_id`` and return the run id."""
    async with AsyncSessionLocal() as db:
        await _set_org(db, org_id)
        team = Team(org_id=org_id, name=f"Artifacts {uuid4().hex[:8]}")
        db.add(team)
        await db.flush()
        session = Session(org_id=org_id, team_id=team.id, thread_id=uuid4().hex)
        db.add(session)
        await db.flush()
        run = Run(org_id=org_id, session_id=session.id, query="produce a file")
        db.add(run)
        await db.flush()
        run_id = run.id
        await db.commit()
    return run_id


async def _create_artifact(org_id: UUID, run_id: UUID, **kwargs: object) -> UUID:
    """Create one artifact via the real service (the seam tools use in Slice 2)."""
    settings = get_settings()
    async with AsyncSessionLocal() as db:
        await _set_org(db, org_id)
        svc = ArtifactService(db, build_storage(settings.ARTIFACTS_DIR), settings, org_id)
        art = await svc.create_artifact(run_id=run_id, **kwargs)  # type: ignore[arg-type]
        artifact_id = art.id
        await db.commit()
    return artifact_id


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_text_artifact_downloads_via_signed_url_and_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ARTIFACTS_DIR", str(tmp_path))
    org_id = await _make_org()
    run_id = await _seed_run(org_id)
    source = "print('hello from an artifact')\n"
    artifact_id = await _create_artifact(
        org_id,
        run_id,
        kind="code",
        filename="main.py",
        mime_type="text/x-python",
        content=source,
        content_format="code",
    )

    async with _client() as client:
        # Metadata: small text inlines as a preview (§12), exposes a signed URL (§10).
        meta = await client.get(f"/artifacts/{artifact_id}", headers={"X-Org-Id": str(org_id)})
        assert meta.status_code == 200, meta.text
        body = meta.json()
        assert body["kind"] == "code"
        assert body["filename"] == "main.py"
        assert body["preview"] == source
        assert body["current_version"] == 1
        assert len(body["versions"]) == 1
        signed_url = body["download_url"]
        assert "token=" in signed_url

        # Download via the signed URL — no auth header needed (public link, §15).
        dl = await client.get(signed_url)
        assert dl.status_code == 200, dl.text
        assert dl.content == source.encode("utf-8")
        assert 'filename="main.py"' in dl.headers["content-disposition"]

        # Download via the authenticated path (management UI) — same bytes.
        dl2 = await client.get(
            f"/artifacts/{artifact_id}/download", headers={"X-Org-Id": str(org_id)}
        )
        assert dl2.status_code == 200
        assert dl2.content == source.encode("utf-8")

        # The run lists its artifact (§14).
        listed = await client.get(f"/runs/{run_id}/artifacts", headers={"X-Org-Id": str(org_id)})
        assert listed.status_code == 200
        assert [a["id"] for a in listed.json()] == [str(artifact_id)]


async def test_binary_artifact_spills_to_storage_and_downloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ARTIFACTS_DIR", str(tmp_path))
    org_id = await _make_org()
    run_id = await _seed_run(org_id)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    artifact_id = await _create_artifact(
        org_id,
        run_id,
        kind="image",
        filename="chart.png",
        mime_type="image/png",
        data=png,
    )

    # Binary always lives in object storage: storage_ref set, content NULL (§7).
    async with AsyncSessionLocal() as db:
        await _set_org(db, org_id)
        row = await db.get(Artifact, artifact_id)
        assert row is not None
        assert row.storage_ref is not None
        assert row.content is None
        assert row.size_bytes == len(png)

    async with _client() as client:
        meta = await client.get(f"/artifacts/{artifact_id}", headers={"X-Org-Id": str(org_id)})
        assert meta.json()["preview"] is None  # binary has no inline preview
        dl = await client.get(
            f"/artifacts/{artifact_id}/download", headers={"X-Org-Id": str(org_id)}
        )
        assert dl.status_code == 200
        assert dl.content == png
        assert dl.headers["content-type"].startswith("image/png")


async def test_download_is_rls_scoped_to_org(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ARTIFACTS_DIR", str(tmp_path))
    org_id = await _make_org()
    other_org = await _make_org()
    run_id = await _seed_run(org_id)
    artifact_id = await _create_artifact(
        org_id,
        run_id,
        kind="markdown",
        filename="notes.md",
        mime_type="text/markdown",
        content="# hi",
    )

    async with _client() as client:
        # A different org cannot see the metadata or download it (RLS + org filter, §15).
        assert (
            await client.get(f"/artifacts/{artifact_id}", headers={"X-Org-Id": str(other_org)})
        ).status_code == 404
        assert (
            await client.get(
                f"/artifacts/{artifact_id}/download", headers={"X-Org-Id": str(other_org)}
            )
        ).status_code == 404


async def test_tampered_token_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ARTIFACTS_DIR", str(tmp_path))
    org_id = await _make_org()
    run_id = await _seed_run(org_id)
    artifact_id = await _create_artifact(
        org_id,
        run_id,
        kind="json",
        filename="data.json",
        mime_type="application/json",
        content="{}",
    )

    async with _client() as client:
        url = (
            await client.get(f"/artifacts/{artifact_id}", headers={"X-Org-Id": str(org_id)})
        ).json()["download_url"]
        # Corrupt the token's signature → 403, no bytes served (§15).
        bad = await client.get(url[:-2] + ("AA" if not url.endswith("AA") else "BB"))
        assert bad.status_code == 403


async def test_specific_version_downloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ARTIFACTS_DIR", str(tmp_path))
    org_id = await _make_org()
    run_id = await _seed_run(org_id)
    artifact_id = await _create_artifact(
        org_id, run_id, kind="csv", filename="rows.csv", mime_type="text/csv", content="a,b\n1,2\n"
    )

    async with _client() as client:
        dl = await client.get(
            f"/artifacts/{artifact_id}/versions/1/download", headers={"X-Org-Id": str(org_id)}
        )
        assert dl.status_code == 200
        assert dl.content == b"a,b\n1,2\n"
        # A non-existent version is a clean 404.
        missing = await client.get(
            f"/artifacts/{artifact_id}/versions/9/download", headers={"X-Org-Id": str(org_id)}
        )
        assert missing.status_code == 404


async def test_oversize_artifact_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "ARTIFACTS_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "ARTIFACT_MAX_BYTES", 16)  # tiny cap for the test
    org_id = await _make_org()
    run_id = await _seed_run(org_id)
    with pytest.raises(ArtifactTooLarge):
        await _create_artifact(
            org_id,
            run_id,
            kind="code",
            filename="big.py",
            mime_type="text/x-python",
            content="x" * 100,
        )
