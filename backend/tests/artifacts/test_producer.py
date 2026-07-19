"""Slice-2 vertical: the producer emits a file that streams in and downloads (§19).

Drives the real :class:`ArtifactAgentProducer` over a **real** create_agent ReAct loop
(offline, via the scripted model) against a **real** migrated Postgres: a producer-model
tool call → ``write_code_file`` → an ``artifacts`` row + version persisted and committed
→ a standard ``tool_result`` event carrying the descriptor (§11.1) → downloadable via the
signed URL on that descriptor (Slice-1 endpoint). This is "prove a file streams in and
downloads" end-to-end.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage
from sqlalchemy import text

from app.artifacts.producer import ArtifactAgentProducer
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
    """Dispose the shared engine pool inside each test's loop (see Slice-1 rationale)."""
    yield
    await engine.dispose()


async def _seed_run() -> tuple[UUID, UUID]:
    """Seed org → team → session → run; return ``(org_id, run_id)``."""
    async with AsyncSessionLocal() as db:
        org = Organization(name="Producer Org", slug=f"prod-{uuid4().hex[:10]}")
        db.add(org)
        await db.flush()
        org_id = org.id
        await db.execute(
            text("SELECT set_config('app.current_org', :o, true)"), {"o": str(org_id)}
        )
        team = Team(org_id=org_id, name=f"Producer {uuid4().hex[:8]}")
        db.add(team)
        await db.flush()
        session = Session(org_id=org_id, team_id=team.id, thread_id=uuid4().hex)
        db.add(session)
        await db.flush()
        run = Run(org_id=org_id, session_id=session.id, query="write a python script")
        db.add(run)
        await db.flush()
        run_id = run.id
        await db.commit()
    return org_id, run_id


async def _seed_chat_run() -> tuple[UUID, UUID]:
    """Seed org → team → **conversation** → run (team chat); return ``(org_id, run_id)``.

    Proves artifacts work in team **chat**: a chat turn's run is owned by a conversation
    (the run XOR), and goes through the *same* producer-wired ``drive_run`` a session does.
    """
    from app.db.models import Conversation

    async with AsyncSessionLocal() as db:
        org = Organization(name="Chat Org", slug=f"chat-{uuid4().hex[:10]}")
        db.add(org)
        await db.flush()
        org_id = org.id
        await db.execute(
            text("SELECT set_config('app.current_org', :o, true)"), {"o": str(org_id)}
        )
        team = Team(org_id=org_id, name=f"Chat {uuid4().hex[:8]}")
        db.add(team)
        await db.flush()
        conversation = Conversation(org_id=org_id, team_id=team.id, thread_id=uuid4().hex)
        db.add(conversation)
        await db.flush()
        run = Run(org_id=org_id, conversation_id=conversation.id, query="write a script")
        db.add(run)
        await db.flush()
        run_id = run.id
        await db.commit()
    return org_id, run_id


async def test_producer_code_file_works_in_team_chat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A downloadable CODE file is produced for a team-CHAT (conversation) run too."""
    monkeypatch.setattr(get_settings(), "ARTIFACTS_DIR", str(tmp_path))
    org_id, run_id = await _seed_chat_run()
    model = ScriptedToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_code_file",
                        "args": {
                            "filename": "app.py",
                            "language": "python",
                            "content": "def main():\n    print('chat-built')\n",
                        },
                        "id": "call_1",
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
            model=model, service=service, run_id=run_id, producer_agent_id=None
        )
        events = await producer.produce(
            goal="write a python script", success_criteria=[], final_output="agreed", ranked=[]
        )

    attachment = [e for e in events if e["type"] == "tool_result"][0]["data"]["attachment"]
    assert attachment["kind"] == "code"
    assert attachment["filename"] == "app.py"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        dl = await client.get(attachment["download_url"])
        assert dl.status_code == 200
        assert dl.content == b"def main():\n    print('chat-built')\n"


async def test_producer_emits_downloadable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "ARTIFACTS_DIR", str(tmp_path))
    org_id, run_id = await _seed_run()

    # Scripted producer model: call write_code_file, then end the loop (no tool calls).
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
                            "content": "print('hi from the team')\n",
                        },
                        "id": "call_1",
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
            model=model, service=service, run_id=run_id, producer_agent_id=None
        )
        events = await producer.produce(
            goal="write a python script that prints a greeting",
            success_criteria=[],
            final_output="The script should print a greeting.",
            ranked=[],
        )

    # One standard tool_result event carrying the artifact descriptor (§11.1).
    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert len(tool_results) == 1, events
    attachment = tool_results[0]["data"]["attachment"]
    assert attachment["kind"] == "code"
    assert attachment["filename"] == "main.py"
    assert attachment["status"] == "ready"
    assert attachment["preview"] == "print('hi from the team')\n"
    download_url = attachment["download_url"]
    assert "token=" in download_url

    # The committed artifact downloads via the signed URL on its descriptor.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        dl = await client.get(download_url)
        assert dl.status_code == 200, dl.text
        assert dl.content == b"print('hi from the team')\n"
        assert 'filename="main.py"' in dl.headers["content-disposition"]


async def test_producer_emits_downloadable_docx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The producer's office tool (create_docx) yields a real, openable .docx (§5)."""
    import io

    from docx import Document

    monkeypatch.setattr(get_settings(), "ARTIFACTS_DIR", str(tmp_path))
    org_id, run_id = await _seed_run()
    model = ScriptedToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_docx",
                        "args": {
                            "filename": "summary.docx",
                            "title": "Team Summary",
                            "sections": [{"heading": "Findings", "body": "We agreed on X."}],
                        },
                        "id": "call_1",
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
            model=model,
            service=service,
            run_id=run_id,
            producer_agent_id=None,
            doc_chart=True,
        )
        events = await producer.produce(
            goal="write a one-page summary document",
            success_criteria=[],
            final_output="The team agreed on X.",
            ranked=[],
        )

    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert len(tool_results) == 1
    attachment = tool_results[0]["data"]["attachment"]
    assert attachment["kind"] == "docx"
    assert attachment["filename"] == "summary.docx"
    assert attachment["preview"] is None  # binary → no inline preview

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        dl = await client.get(attachment["download_url"])
        assert dl.status_code == 200
        assert dl.content[:2] == b"PK"  # OOXML zip
        # The bytes re-open as a real Word document carrying the produced text.
        texts = [p.text for p in Document(io.BytesIO(dl.content)).paragraphs]
        assert "Team Summary" in texts and "Findings" in texts


async def test_producer_prose_only_emits_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A prose-only task (model replies NONE) produces no artifacts (§2A rule 4)."""
    monkeypatch.setattr(get_settings(), "ARTIFACTS_DIR", str(tmp_path))
    org_id, run_id = await _seed_run()
    model = ScriptedToolCallingModel(responses=[AIMessage(content="NONE")])

    async with AsyncSessionLocal() as db:
        await db.execute(
            text("SELECT set_config('app.current_org', :o, false)"), {"o": str(org_id)}
        )
        service = ArtifactService(db, build_storage(str(tmp_path)), get_settings(), org_id)
        producer = ArtifactAgentProducer(
            model=model, service=service, run_id=run_id, producer_agent_id=None
        )
        events = await producer.produce(
            goal="summarize the discussion",
            success_criteria=[],
            final_output="A short summary.",
            ranked=[],
        )

    assert [e for e in events if e["type"] == "tool_result"] == []
