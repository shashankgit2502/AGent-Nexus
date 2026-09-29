"""Slice-5: create_archive (.zip) bundling (ARTIFACTS §5/§14/§19).

Covers the zip generator (valid archive, duplicate-name disambiguation, empty rejected),
the `create_archive` tool over a fake sink (bundles resolved members; refuses when there
is nothing to bundle), and an end-to-end producer run that creates two files then bundles
them into a **working** .zip downloaded and re-opened with `zipfile`.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage
from sqlalchemy import text

from app.artifacts.descriptor import ArtifactRef
from app.artifacts.generators import build_archive
from app.artifacts.producer import ArtifactAgentProducer
from app.artifacts.service import ArtifactService
from app.artifacts.storage import build_storage
from app.core.config import get_settings
from app.db.models import Organization, Run, Session, Team
from app.db.session import AsyncSessionLocal, engine
from app.main import app
from app.tools.artifacts_media import make_archive_tool
from tests.agents._fakes import ScriptedToolCallingModel

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_after_test() -> object:
    yield
    await engine.dispose()


# ── pure generator (no DB) ────────────────────────────────────────────────────


def test_build_archive_is_a_valid_zip_with_members() -> None:
    data = build_archive([("a.py", b"print(1)"), ("notes.md", b"# hi")])
    assert data[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert set(zf.namelist()) == {"a.py", "notes.md"}
        assert zf.read("a.py") == b"print(1)"


def test_build_archive_disambiguates_duplicate_names() -> None:
    data = build_archive([("main.py", b"v1"), ("main.py", b"v2")])
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        assert "main.py" in names and "main_1.py" in names
        assert len(names) == 2


def test_build_archive_rejects_empty() -> None:
    with pytest.raises(ValueError):
        build_archive([])


# ── create_archive tool (fake sink) ───────────────────────────────────────────


class _FakeArchiveSink:
    def __init__(self, members: list[tuple[str, bytes]]) -> None:
        self._members = members
        self.writes: list[dict[str, object]] = []

    async def load_members(self, artifact_ids: list[str] | None) -> list[tuple[str, bytes]]:
        return self._members

    async def write_binary(
        self, *, kind: str, filename: str, mime_type: str, data: bytes, tool: str
    ) -> ArtifactRef:
        self.writes.append({"kind": kind, "filename": filename, "mime": mime_type, "data": data})
        return ArtifactRef(artifact_id=uuid4(), kind=kind, filename=filename, download_url="/d")


async def test_create_archive_tool_bundles_members() -> None:
    sink = _FakeArchiveSink([("a.py", b"x"), ("b.md", b"y")])
    tool = make_archive_tool(sink)  # type: ignore[arg-type]
    out = await tool.ainvoke({"filename": "project", "artifact_ids": ["i1", "i2"]})
    assert "artifact_id=" in out
    write = sink.writes[0]
    assert write["kind"] == "archive"
    assert write["filename"] == "project.zip"
    with zipfile.ZipFile(io.BytesIO(write["data"])) as zf:  # type: ignore[arg-type]
        assert set(zf.namelist()) == {"a.py", "b.md"}


async def test_create_archive_tool_refuses_when_empty() -> None:
    sink = _FakeArchiveSink([])
    tool = make_archive_tool(sink)  # type: ignore[arg-type]
    out = await tool.ainvoke({"filename": "project", "artifact_ids": []})
    assert out.startswith("refused")
    assert sink.writes == []


# ── end-to-end producer run (real DB) ─────────────────────────────────────────


async def _seed_run() -> tuple[UUID, UUID]:
    async with AsyncSessionLocal() as db:
        org = Organization(name="Zip Org", slug=f"zip-{uuid4().hex[:10]}")
        db.add(org)
        await db.flush()
        org_id = org.id
        await db.execute(
            text("SELECT set_config('app.current_org', :o, true)"), {"o": str(org_id)}
        )
        team = Team(org_id=org_id, name=f"Zip {uuid4().hex[:8]}")
        db.add(team)
        await db.flush()
        session = Session(org_id=org_id, team_id=team.id, thread_id=uuid4().hex)
        db.add(session)
        await db.flush()
        run = Run(org_id=org_id, session_id=session.id, query="scaffold a project")
        db.add(run)
        await db.flush()
        run_id = run.id
        await db.commit()
    return org_id, run_id


async def test_producer_bundles_two_files_into_working_zip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ARTIFACTS_DIR", str(tmp_path))
    org_id, run_id = await _seed_run()

    # Producer: create two files, then bundle EVERYTHING (empty artifact_ids).
    model = ScriptedToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_code_file",
                        "args": {
                            "filename": "main.py",
                            "language": "python",
                            "content": "print('a')\n",
                        },
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_code_file",
                        "args": {
                            "filename": "util.py",
                            "language": "python",
                            "content": "X = 1\n",
                        },
                        "id": "c2",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_archive",
                        "args": {"filename": "project", "artifact_ids": []},
                        "id": "c3",
                    }
                ],
            ),
            AIMessage(content="Done."),
        ]
    )

    async with AsyncSessionLocal() as db:
        await db.execute(
            text("SELECT set_config('app.current_org', :o, false)"), {"o": str(org_id)}
        )
        service = ArtifactService(db, build_storage(str(tmp_path)), get_settings(), org_id)
        producer = ArtifactAgentProducer(
            model=model, service=service, run_id=run_id, producer_agent_id=None, doc_chart=True
        )
        events = await producer.produce(
            goal="scaffold a tiny project", success_criteria=[], final_output="agreed", ranked=[]
        )

    archives = [
        e
        for e in events
        if e["type"] == "tool_result" and e["data"]["attachment"]["kind"] == "archive"
    ]
    assert len(archives) == 1
    archive_attachment = archives[0]["data"]["attachment"]
    assert archive_attachment["filename"] == "project.zip"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        dl = await client.get(archive_attachment["download_url"])
        assert dl.status_code == 200
        assert dl.content[:2] == b"PK"
        with zipfile.ZipFile(io.BytesIO(dl.content)) as zf:
            assert set(zf.namelist()) == {"main.py", "util.py"}  # both files, no nested zip
            assert zf.read("main.py") == b"print('a')\n"
